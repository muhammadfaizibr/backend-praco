from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django_ckeditor_5.fields import CKEditor5Field
from django.utils.text import slugify
from django.core.validators import MinValueValidator
from decimal import Decimal, ROUND_HALF_UP
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

class Category(models.Model):
    """
    Represents a product category with a name, slug, description, and images.
    """
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True, help_text="URL-friendly identifier, auto-generated if blank")
    description = CKEditor5Field(blank=True)
    image = models.ImageField(upload_to='category_images/', blank=True, null=True)
    slider_image = models.ImageField(upload_to='category_slider_images/', blank=True, null=True, help_text="Optional image for slider display")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['slug']),
            models.Index(fields=['created_at']),
        ]
        verbose_name = 'category'
        verbose_name_plural = 'categories'

    def clean(self):
        if not self.name:
            raise ValidationError({"name": "Category name is required."})

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
            base_slug = self.slug
            counter = 1
            while Category.objects.filter(slug=self.slug).exclude(id=self.id).exists():
                self.slug = f"{base_slug}-{counter}"
                counter += 1
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Product(models.Model):
    """
    Represents a product within a category, with a name, description, and images.
    """
    category = models.ForeignKey('Category', on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, blank=True, help_text="URL-friendly identifier, auto-generated if blank")
    description = CKEditor5Field()
    is_new = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['category', 'name']),
            models.Index(fields=['created_at']),
        ]
        verbose_name = 'product'
        verbose_name_plural = 'products'

    def clean(self):
        errors = {}
        if not self.name:
            errors['name'] = "Product name is required."
        elif not self.description:
            errors['description'] = "Product description is required."
        elif not self.category:
            errors['category'] = "Please select a category for the product."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
            base_slug = self.slug
            counter = 1
            while Product.objects.filter(slug=self.slug).exclude(id=self.id).exists():
                self.slug = f"{base_slug}-{counter}"
                counter += 1
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.category.name} - {self.name}"

class ProductImage(models.Model):
    """
    Stores images associated with a product.
    """
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='product_images/')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['product']),
        ]
        verbose_name = 'product image'
        verbose_name_plural = 'product images'

    def clean(self):
        errors = {}
        if not self.image:
            errors['image'] = "Please upload an image for the product."
        elif not self.product:
            errors['product'] = "Please select a product for this image."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Image for {self.product.name}"

class ProductVariant(models.Model):
    """
    Represents a variant of a product with specific attributes like pack/pallet units.
    """
    SHOW_UNITS_PER_CHOICES = (
        ('pack', 'Pack'),
        ('both', 'Both (Pack & Pallet)'),
    )
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('active', 'Active'),
    )

    product = models.ForeignKey('Product', on_delete=models.CASCADE, related_name='product_variants')
    name = models.CharField(max_length=255)
    units_per_pack = models.PositiveIntegerField(default=6, help_text="Number of units per pack")
    units_per_pallet = models.PositiveIntegerField(default=0, blank=True, help_text="Number of units per pallet")
    show_units_per = models.CharField(max_length=10, choices=SHOW_UNITS_PER_CHOICES, default='pack')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft', editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['product', 'name']),
            models.Index(fields=['created_at']),
        ]
        verbose_name = 'product variant'
        verbose_name_plural = 'product variants'

    def clean(self):
        errors = {}
        if not self.product_id:
            errors['product'] = "Please select a product for the variant."
        elif not self.name:
            errors['name'] = "Variant name is required."
        elif self.units_per_pack <= 0:
            errors['units_per_pack'] = "Units per pack must be a positive number."

        # Validate units_per_pallet using if-elif to avoid multiple errors
        if self.show_units_per == 'both':
            if self.units_per_pallet is None or self.units_per_pallet <= 0:
                errors['units_per_pallet'] = "Units per pallet must be a positive number when showing both pack and pallet."
            elif self.units_per_pallet <= self.units_per_pack:
                errors['units_per_pallet'] = "Units per pallet must be greater than units per pack when showing both."
            elif self.units_per_pallet % self.units_per_pack != 0:
                errors['units_per_pallet'] = (
                    f"Units per pallet must be a multiple of units per pack ({self.units_per_pack}) "
                    "when showing both pack and pallet."
                )
        elif self.units_per_pallet is not None and self.units_per_pallet != 0:
            errors['units_per_pallet'] = "Units per pallet must be 0 or blank when showing only pack."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.name} - {self.name}"

class PricingTier(models.Model):
    """
    Defines pricing tiers for product variants based on quantity ranges and type (pack/pallet).
    """
    TIER_TYPES = (
        ('pack', 'Pack'),
        ('pallet', 'Pallet'),
    )

    product_variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name='pricing_tiers')
    tier_type = models.CharField(max_length=10, choices=TIER_TYPES)
    range_start = models.PositiveIntegerField()
    range_end = models.PositiveIntegerField(null=True, blank=True, help_text="Leave blank if 'No End Range' is checked")
    no_end_range = models.BooleanField(default=False, help_text="Check if this tier has no end range (e.g., X+)")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['product_variant', 'tier_type']),
            models.Index(fields=['created_at']),
        ]
        verbose_name = 'pricing tier'
        verbose_name_plural = 'pricing tiers'

    def clean(self):
        errors = {}
        if not self.product_variant:
            errors['product_variant'] = "Please select a product variant for this pricing tier."
        elif self.range_start is None or self.range_start <= 0:
            errors['range_start'] = "Range start must be a positive number."
        elif self.no_end_range and self.range_end is not None:
            errors['range_end'] = "Range end must be blank when 'No End Range' is checked."
        elif not self.no_end_range and self.range_end is None:
            errors['range_end'] = "Range end is required unless 'No End Range' is checked."
        elif not self.no_end_range and self.range_end <= self.range_start:
            errors['range_end'] = "Range end must be greater than range start."

        # Validate tier_type against product_variant.show_units_per
        if self.product_variant:
            if self.product_variant.show_units_per == 'pack' and self.tier_type != 'pack':
                errors['tier_type'] = "Only 'Pack' tier type is allowed when the variant is set to show only pack."
            elif self.product_variant.show_units_per == 'both' and self.tier_type not in ['pack', 'pallet']:
                errors['tier_type'] = "Tier type must be either 'Pack' or 'Pallet' when showing both."

        # Check for overlapping ranges
        if self.product_variant:
            existing_tiers = PricingTier.objects.filter(
                product_variant=self.product_variant,
                tier_type=self.tier_type
            ).exclude(id=self.id)
            for tier in existing_tiers:
                current_end = float('inf') if self.no_end_range else self.range_end
                tier_end = float('inf') if tier.no_end_range else tier.range_end
                if self.range_start <= tier_end and current_end >= tier.range_start:
                    errors['range_start'] = (
                        f"Range {self.range_start}-{'+' if self.no_end_range else self.range_end} overlaps with "
                        f"existing range {tier.range_start}-{'+' if tier.no_end_range else tier.range_end} for {self.tier_type}."
                    )
                    break

        if errors:
            raise ValidationError(errors)

    def check_pricing_tiers_conditions(self):
        """
        Check if the pricing tiers for the associated ProductVariant meet the conditions to set status='active'.
        """
        try:
            pricing_tiers = self.product_variant.pricing_tiers.all()
            pack_tiers = [tier for tier in pricing_tiers if tier.tier_type == 'pack']
            pallet_tiers = [tier for tier in pricing_tiers if tier.tier_type == 'pallet']

            if self.product_variant.show_units_per == 'pack':
                if not pack_tiers or pallet_tiers:
                    return False
                pack_no_end = [tier for tier in pack_tiers if tier.no_end_range]
                if len(pack_no_end) != 1:
                    return False
                for tier in pack_tiers:
                    if not tier.no_end_range and tier.range_end is None:
                        return False
            elif self.product_variant.show_units_per == 'both':
                if not pack_tiers or not pallet_tiers:
                    return False
                pack_no_end = [tier for tier in pack_tiers if tier.no_end_range]
                pallet_no_end = [tier for tier in pallet_tiers if tier.no_end_range]
                if len(pack_no_end) != 1 or len(pallet_no_end) != 1:
                    return False
                for tier in pack_tiers + pallet_tiers:
                    if not tier.no_end_range and tier.range_end is None:
                        return False
            return True
        except Exception:
            return False

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        try:
            if self.check_pricing_tiers_conditions():
                self.product_variant.status = 'active'
            else:
                self.product_variant.status = 'draft'
            self.product_variant.save()
        except Exception:
            pass

    def __str__(self):
        range_str = f"{self.range_start}-" + ("+" if self.no_end_range else str(self.range_end))
        return f"{self.product_variant} - {self.tier_type} - {range_str}"

@receiver(post_delete, sender=PricingTier)
def update_product_variant_status_on_delete(sender, instance, **kwargs):
    try:
        product_variant = instance.product_variant
        if not product_variant.pricing_tiers.exists() or not instance.check_pricing_tiers_conditions():
            product_variant.status = 'draft'
            product_variant.save()
    except Exception:
        pass

class PricingTierData(models.Model):
    """
    Stores pricing data for an item within a pricing tier, with price per unit.
    """
    item = models.ForeignKey('Item', on_delete=models.CASCADE, related_name='pricing_tier_data')
    pricing_tier = models.ForeignKey(PricingTier, on_delete=models.CASCADE, related_name='pricing_data')
    price = models.DecimalField(max_digits=12, decimal_places=2, help_text="Price per unit")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('item', 'pricing_tier')
        indexes = [
            models.Index(fields=['item', 'pricing_tier']),
            models.Index(fields=['created_at']),
        ]
        verbose_name = 'pricing tier data'
        verbose_name_plural = 'pricing tier data'

    def clean(self):
        errors = {}
        if not self.item:
            errors['item'] = "Please select an item for this pricing data."
        elif not self.pricing_tier:
            errors['pricing_tier'] = "Please select a pricing tier for this pricing data."
        elif self.pricing_tier.product_variant != self.item.product_variant:
            errors['pricing_tier'] = "Pricing tier must belong to the same product variant as the item."
        elif self.price is None or self.price <= 0:
            errors['price'] = "Price per unit must be a positive number."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.item} - {self.pricing_tier} - Price per unit: {self.price}"

class TableField(models.Model):
    """
    Defines custom fields for product variants to store additional item data.
    """
    FIELD_TYPES = (
        ('text', 'Text'),
        ('number', 'Number'),
        ('image', 'Image'),
    )
    RESERVED_NAMES = [
        'title', 'status', 'is_physical_product', 'weight', 'weight_unit',
        'track_inventory', 'stock', 'sku', 'image'
    ]

    product_variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name='table_fields')
    name = models.CharField(max_length=255)
    field_type = models.CharField(max_length=20, choices=FIELD_TYPES, db_index=True)
    long_field = models.BooleanField(default=False, help_text="Check if this field requires more display space (e.g., for long text)")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('product_variant', 'name')
        indexes = [
            models.Index(fields=['product_variant', 'name']),
            models.Index(fields=['field_type']),
        ]
        verbose_name = 'table field'
        verbose_name_plural = 'table fields'

    def clean(self):
        errors = {}
        if not self.name:
            errors['name'] = "Table field name is required."
        elif self.name.lower() in self.RESERVED_NAMES:
            errors['name'] = f"The name '{self.name}' is reserved and cannot be used."
        elif not self.field_type:
            errors['field_type'] = "Please select a field type for the table field."
        elif not self.product_variant:
            errors['product_variant'] = "Please select a product variant for the table field."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product_variant.name} - {self.name} ({self.field_type}, {'Long' if self.long_field else 'Short'})"

class Item(models.Model):
    """
    Represents a specific item within a product variant with attributes like SKU, stock, and dimensions.
    """
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('active', 'Active'),
    )
    WEIGHT_UNIT_CHOICES = (
        ('lb', 'Pounds (lb)'),
        ('kg', 'Kilograms (kg)'),
        ('oz', 'Ounces (oz)'),
        ('g', 'Grams (g)'),
    )
    MEASUREMENT_UNIT_CHOICES = (
        ('MM', 'Millimeters'),
        ('CM', 'Centimeters'),
        ('IN', 'Inches'),
        ('M', 'Meters'),
    )

    product_variant = models.ForeignKey('ProductVariant', on_delete=models.CASCADE, related_name='items', null=False, blank=False)
    title = models.CharField(max_length=255, blank=True, null=True)
    sku = models.CharField(max_length=100, unique=True)
    is_physical_product = models.BooleanField(default=False)
    weight = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    weight_unit = models.CharField(max_length=2, choices=WEIGHT_UNIT_CHOICES, blank=True, null=True)
    track_inventory = models.BooleanField(default=False)
    stock = models.IntegerField(blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    created_at = models.DateTimeField(auto_now_add=True)
    height = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, validators=[MinValueValidator(0.0)])
    width = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, validators=[MinValueValidator(0.0)])
    length = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, validators=[MinValueValidator(0.0)])
    measurement_unit = models.CharField(max_length=2, choices=MEASUREMENT_UNIT_CHOICES, blank=True, null=True)
    height_in_inches = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        blank=True, 
        null=True, 
        editable=False, 
        help_text="Height converted to inches (automatically calculated)."
    )
    width_in_inches = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        blank=True, 
        null=True, 
        editable=False, 
        help_text="Width converted to inches (automatically calculated)."
    )
    length_in_inches = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        blank=True, 
        null=True, 
        editable=False, 
        help_text="Length converted to inches (automatically calculated)."
    )

    class Meta:
        indexes = [
            models.Index(fields=['product_variant']),
            models.Index(fields=['sku']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]
        verbose_name = 'item'
        verbose_name_plural = 'items'

    def convert_to_inches(self, value, unit):
        """
        Convert a dimension value from the given unit to inches.
        """
        if value is None:
            return None
        value = Decimal(str(value))  # Ensure value is a Decimal
        if unit == 'MM':
            return (value * Decimal('0.0393701')).quantize(Decimal('0.01'))
        elif unit == 'CM':
            return (value * Decimal('0.393701')).quantize(Decimal('0.01'))
        elif unit == 'M':
            return (value * Decimal('39.3701')).quantize(Decimal('0.01'))
        elif unit == 'IN':
            return value.quantize(Decimal('0.01'))
        return None

    def clean(self):
        errors = {}

        # Validate SKU
        if not self.sku:
            errors['sku'] = "SKU is required."

        # Validate product_variant
        try:
            if not self.product_variant:
                errors['product_variant'] = "Please select a product variant for the item."
        except AttributeError as e:
            raise ValidationError(errors) from e
        
        else:
            # Safely access related objects for category-based validation
            try:
                category_name = self.product_variant.product.category.name.lower() if (
                    self.product_variant and 
                    hasattr(self.product_variant, 'product') and 
                    self.product_variant.product and 
                    hasattr(self.product_variant.product, 'category') and 
                    self.product_variant.product.category
                ) else ''
            except AttributeError as e:
                errors['product_variant'] = "Invalid product variant: related product or category is missing."
                raise ValidationError(errors) from e

            # Category-based validation for dimensions
            required_categories = ['box', 'boxes', 'postal', 'postals', 'bag', 'bags']
            if category_name in required_categories:
                if self.height is None or self.height <= 0:
                    errors['height'] = "Height must be a positive number for this category."
                if self.width is None or self.width <= 0:
                    errors['width'] = "Width must be a positive number for this category."
                if self.length is None or self.length <= 0:
                    errors['length'] = "Length must be a positive number for this category."
                if not self.measurement_unit:
                    errors['measurement_unit'] = "Please select a measurement unit for this category."
                if self.measurement_unit not in ['MM', 'CM', 'IN', 'M']:
                    errors['measurement_unit'] = "Please select a valid measurement unit (MM, CM, IN, M)."
            else:
                self.height = None
                self.width = None
                self.length = None
                self.measurement_unit = None
                self.height_in_inches = None
                self.width_in_inches = None
                self.length_in_inches = None

            # Validate PricingTierData entries for status
            if self.pk and self.status == 'active':
                try:
                    pricing_tiers = self.product_variant.pricing_tiers.all()
                    existing_pricing_data = set(self.pricing_tier_data.values_list('pricing_tier_id', flat=True))
                    missing_tiers = [tier for tier in pricing_tiers if tier.id not in existing_pricing_data]
                    if missing_tiers:
                        missing_tier_names = [f"{tier.tier_type} ({tier.range_start}-{'+' if tier.no_end_range else tier.range_end})" for tier in missing_tiers]
                        errors['status'] = f"Cannot set status to 'Active'. Missing pricing data for: {', '.join(missing_tier_names)}."
                except AttributeError as e:
                    errors['status'] = "Unable to validate pricing tiers due to invalid product variant relationship."
                    raise ValidationError(errors) from e

        # Validate physical product details
        if self.is_physical_product:
            if self.weight is None or self.weight <= 0:
                errors['weight'] = "Weight must be a positive number for physical products."
            if not self.weight_unit:
                errors['weight_unit'] = "Please select a weight unit for physical products."
        else:
            self.weight = None
            self.weight_unit = None

        # Validate inventory tracking
        if self.track_inventory:
            if self.stock is None or self.stock < 0:
                errors['stock'] = "Stock must be a non-negative number when tracking inventory."
            if not self.title:
                errors['title'] = "Title is required when tracking inventory."
            # Validate that stock is a multiple of product_variant.units_per_pack
            if self.product_variant and self.stock is not None:
                units_per_pack = self.product_variant.units_per_pack
                if units_per_pack > 0 and self.stock % units_per_pack != 0:
                    errors['stock'] = f"Stock must be a multiple of the product variant's units per pack ({units_per_pack}). Current stock: {self.stock}."
        else:
            self.stock = None
            self.title = None

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # Perform validation first
        self.full_clean()

        # Convert dimensions to inches if measurement_unit is set
        if self.measurement_unit and self.height is not None and self.width is not None and self.length is not None:
            self.height_in_inches = self.convert_to_inches(self.height, self.measurement_unit)
            self.width_in_inches = self.convert_to_inches(self.width, self.measurement_unit)
            self.length_in_inches = self.convert_to_inches(self.length, self.measurement_unit)
        else:
            self.height_in_inches = None
            self.width_in_inches = None
            self.length_in_inches = None

        # Save the instance
        super().save(*args, **kwargs)

        # Update status based on pricing tier data
        if self.pk:
            try:
                pricing_tiers = self.product_variant.pricing_tiers.all()
                existing_pricing_data = set(self.pricing_tier_data.values_list('pricing_tier_id', flat=True))
                self.status = 'active' if all(tier.id in existing_pricing_data for tier in pricing_tiers) else 'draft'
                super().save(update_fields=['status'])
            except AttributeError as e:
                # Log the error if needed, but don't fail the save operation
                pass

    def __str__(self):
        return f"Item {self.sku} for {self.product_variant.name} ({self.status})"

class ItemImage(models.Model):
    """
    Stores images associated with an item.
    """
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='item_images/')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['item']),
        ]
        verbose_name = 'item image'
        verbose_name_plural = 'item images'

    def clean(self):
        errors = {}
        if not self.item:
            errors['item'] = "Please select an item for this image."
        elif not self.image:
            errors['image'] = "Please upload an image for the item."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Image for {self.item}"

class ItemData(models.Model):
    """
    Stores additional data for an item based on table fields (e.g., text, number, image).
    """
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='data_entries')
    field = models.ForeignKey(TableField, on_delete=models.CASCADE, related_name='data_values')
    value_text = models.TextField(blank=True, null=True)
    value_number = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    value_image = models.ImageField(upload_to='item_data_images/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('item', 'field')
        indexes = [
            models.Index(fields=['item', 'field']),
            models.Index(fields=['created_at']),
        ]
        verbose_name = 'item data'
        verbose_name_plural = 'item data'

    def clean(self):
        errors = {}
        if not self.field:
            errors['field'] = "Please select a table field for this data."
        elif not self.item:
            errors['item'] = "Please select an item for this data."

        if self.value_text == '':
            self.value_text = None
        if self.value_number == '':
            self.value_number = None
        if self.value_image == '':
            self.value_image = None

        if self.field:
            if self.field.field_type == 'text':
                if self.value_text is None:
                    errors['value_text'] = f"Please provide a value for the text field '{self.field.name}'."
                elif self.value_number is not None or self.value_image:
                    errors['value_text'] = f"Field '{self.field.name}' only accepts text values."
            elif self.field.field_type == 'number':
                if self.value_number is None:
                    errors['value_number'] = f"Please provide a number for the field '{self.field.name}'."
                elif self.value_text is not None or self.value_image:
                    errors['value_number'] = f"Field '{self.field.name}' only accepts number values."
            elif self.field.field_type == 'image':
                if not self.value_image:
                    errors['value_image'] = f"Please upload an image for the field '{self.field.name}'."
                elif self.value_text is not None or self.value_number is not None:
                    errors['value_image'] = f"Field '{self.field.name}' only accepts image values."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        if self.field.field_type == 'image' and self.value_image:
            return f"{self.item} - {self.field.name}: {self.value_image.url}"
        return f"{self.item} - {self.field.name}: {self.value_text or self.value_number or '-'}"

class UserExclusivePrice(models.Model):
    """
    Stores exclusive discount percentages for specific users and items.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, help_text="Discount percentage")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'item')
        indexes = [
            models.Index(fields=['user', 'item']),
            models.Index(fields=['created_at']),
        ]
        verbose_name = 'user exclusive price'
        verbose_name_plural = 'user exclusive prices'

    def clean(self):
        errors = {}
        if not self.user:
            errors['user'] = "Please select a user for this exclusive price."
        elif not self.item:
            errors['item'] = "Please select an item for this exclusive price."
        elif self.discount_percentage is None or self.discount_percentage < 0 or self.discount_percentage > 100:
            errors['discount_percentage'] = "Discount percentage must be between 0 and 100."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.email} - {self.item} ({self.discount_percentage}% off)"

class Cart(models.Model):
    """
    Represents a user's shopping cart, storing items before order creation.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='cart',
        help_text="The user associated with this cart."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    subtotal = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        editable=False, 
        default=Decimal('0.00'), 
        help_text="Total price of items in the cart (sum of item subtotals)."
    )
    vat = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('20.00'), 
        help_text="VAT percentage (e.g., 20 for 20%)."
    )
    discount = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('0.00'), 
        help_text="Discount percentage (e.g., 10 for 10%). Automatically set to 10% if subtotal > 600 EUR."
    )
    total = models.DecimalField(
        max_digits=12, 
       

        decimal_places=2, 
        editable=False, 
        default=Decimal('0.00'), 
        help_text="Total after applying VAT and discount (subtotal + VAT - discount)."
    )

    class Meta:
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['created_at']),
        ]
        verbose_name = 'cart'
        verbose_name_plural = 'carts'

    def calculate_subtotal(self):
        total = Decimal('0.00')
        for item in self.items.all():
            total += item.subtotal()
        return total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def calculate_total(self):
        subtotal = self.subtotal
        vat_amount = (subtotal * self.vat) / Decimal('100.00')
        discount_amount = (subtotal * self.discount) / Decimal('100.00')
        total = subtotal + vat_amount - discount_amount
        return total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def save(self, *args, **kwargs):
        if not self.pk:
            super().save(*args, **kwargs)

        old_subtotal = self.subtotal
        self.subtotal = self.calculate_subtotal()

        if self.subtotal > Decimal('600.00'):
            self.discount = Decimal('10.00')

        old_total = self.total
        self.total = self.calculate_total()

        if old_subtotal != self.subtotal or old_total != self.total:
            super().save(*args, **kwargs)

    def __str__(self):
        return f"Cart for {self.user.email}"

    @classmethod
    def get_or_create_cart(cls, user):
        cart, created = cls.objects.get_or_create(user=user)
        return cart, created

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_cart(sender, instance, created, **kwargs):
    if created:
        Cart.objects.get_or_create(user=instance)

class CartItem(models.Model):
    """
    Represents an item in a cart with quantity, pricing tier, and unit type.
    """
    cart = models.ForeignKey('Cart', on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey('Item', on_delete=models.PROTECT, related_name='cart_items')
    pricing_tier = models.ForeignKey('PricingTier', on_delete=models.PROTECT, related_name='cart_items')
    quantity = models.PositiveIntegerField()
    unit_type = models.CharField(max_length=10, choices=(('pack', 'Pack'), ('pallet', 'Pallet')), default='pack')
    per_unit_price = models.DecimalField(max_digits=12, decimal_places=2, help_text="Price per unit from PricingTierData")
    per_pack_price = models.DecimalField(max_digits=12, decimal_places=2, help_text="Price per pack (price per unit * units per pack)")
    subtotal = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        editable=False, 
        default=Decimal('0.00'), 
        help_text="Total cost before user_exclusive_price discount (per pack price * quantity or adjusted for pallet)"
    )
    total_cost = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        help_text="Total cost after user_exclusive_price discount"
    )
    user_exclusive_price = models.ForeignKey('UserExclusivePrice', on_delete=models.SET_NULL, null=True, blank=True, related_name='cartitem_items')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['cart', 'item']),
            models.Index(fields=['pricing_tier']),
            models.Index(fields=['created_at']),
        ]
        unique_together = ('cart', 'item', 'pricing_tier', 'unit_type')
        verbose_name = 'cart item'
        verbose_name_plural = 'cart items'

    @property
    def total_units(self):
        if not self.item or not self.item.product_variant:
            return 0
        units_per_pack = self.item.product_variant.units_per_pack
        units_per_pallet = self.item.product_variant.units_per_pallet
        if self.unit_type == 'pack':
            return self.quantity * units_per_pack
        else:
            return self.quantity * units_per_pallet

    def clean(self):
        errors = {}
        if not self.item:
            errors['item'] = "Please select an item for this cart entry."
        elif not self.pricing_tier:
            errors['pricing_tier'] = "Please select a pricing tier for this cart entry."
        elif self.quantity <= 0:
            errors['quantity'] = "Quantity must be a positive number."

        if self.item and self.pricing_tier:
            if self.pricing_tier.product_variant != self.item.product_variant:
                errors['pricing_tier'] = "Pricing tier must belong to the same product variant as the item."
            elif self.item.product_variant.show_units_per == 'pack' and self.unit_type == 'pallet':
                errors['unit_type'] = "This item only supports pack pricing, not pallet pricing."

            total_units = self.total_units
            units_per_pack = self.item.product_variant.units_per_pack
            units_per_pallet = self.item.product_variant.units_per_pallet

            if self.unit_type == 'pack':
                if self.pricing_tier.tier_type == 'pallet':
                    pass
                elif self.quantity < self.pricing_tier.range_start:
                    errors['quantity'] = (
                        f"Quantity {self.quantity} is below the pricing tier range "
                        f"{self.pricing_tier.range_start}-{'+' if self.pricing_tier.no_end_range else self.pricing_tier.range_end}."
                    )
                elif not self.pricing_tier.no_end_range and self.quantity > self.pricing_tier.range_end:
                    errors['quantity'] = (
                        f"Quantity {self.quantity} exceeds the pricing tier range "
                        f"{self.pricing_tier.range_start}-{self.pricing_tier.range_end}."
                    )
            else:
                if self.pricing_tier.tier_type != 'pallet':
                    errors['pricing_tier'] = "Pricing tier must be 'Pallet' when unit type is 'Pallet'."
                elif self.quantity < self.pricing_tier.range_start:
                    errors['quantity'] = (
                        f"Pallet quantity {self.quantity} is below the pricing tier range "
                        f"{self.pricing_tier.range_start}-{'+' if self.pricing_tier.no_end_range else self.pricing_tier.range_end}."
                    )
                elif not self.pricing_tier.no_end_range and self.quantity > self.pricing_tier.range_end:
                    errors['quantity'] = (
                        f"Pallet quantity {self.quantity} exceeds the pricing tier range "
                        f"{self.pricing_tier.range_start}-{self.pricing_tier.range_end}."
                    )

            pricing_data = PricingTierData.objects.filter(pricing_tier=self.pricing_tier, item=self.item).first()
            if not pricing_data:
                errors['pricing_tier'] = "No pricing data found for this item and pricing tier."
            else:
                expected_per_unit_price = pricing_data.price
                if self.per_unit_price is None:
                    self.per_unit_price = expected_per_unit_price
                elif self.per_unit_price != expected_per_unit_price:
                    errors['per_unit_price'] = (
                        f"Per unit price {self.per_unit_price} does not match the expected price {expected_per_unit_price}."
                    )

                expected_per_pack_price = expected_per_unit_price * Decimal(units_per_pack)
                if self.per_pack_price is None:
                    self.per_pack_price = expected_per_pack_price
                elif self.per_pack_price != expected_per_pack_price:
                    errors['per_pack_price'] = (
                        f"Per pack price {self.per_pack_price} does not match the expected price {expected_per_pack_price}."
                    )

                if self.unit_type == 'pack':
                    if self.pricing_tier.tier_type == 'pack':
                        expected_subtotal = expected_per_pack_price * Decimal(self.quantity)
                    else:
                        total_units = Decimal(self.quantity) * Decimal(units_per_pack)
                        equivalent_pallet_quantity = total_units / Decimal(units_per_pallet)
                        expected_subtotal = equivalent_pallet_quantity * expected_per_pack_price * Decimal(units_per_pallet) / Decimal(units_per_pack)
                else:
                    total_units = Decimal(self.quantity) * Decimal(units_per_pallet)
                    equivalent_pack_quantity = total_units / Decimal(units_per_pack)
                    expected_subtotal = equivalent_pack_quantity * expected_per_pack_price

                expected_subtotal = expected_subtotal.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                if self.subtotal is None:
                    self.subtotal = expected_subtotal
                elif self.subtotal != expected_subtotal:
                    errors['subtotal'] = (
                        f"Subtotal {self.subtotal} does not match the expected subtotal {expected_subtotal}."
                    )

                discount_percentage = self.user_exclusive_price.discount_percentage if self.user_exclusive_price else Decimal('0.00')
                discount = discount_percentage / Decimal('100.00')
                expected_total_cost = expected_subtotal * (Decimal('1.00') - discount)
                expected_total_cost = expected_total_cost.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                if self.total_cost is None:
                    self.total_cost = expected_total_cost
                elif self.total_cost != expected_total_cost:
                    errors['total_cost'] = (
                        f"Total cost {self.total_cost} does not match the expected total cost {expected_total_cost}."
                    )

        if self.item and self.item.track_inventory:
            total_units = self.total_units
            if self.item.stock is None or total_units > self.item.stock:
                errors['quantity'] = (
                    f"Insufficient stock for {self.item.sku}. Available: {self.item.stock or 0} units, Required: {total_units} units."
                )

        if self.user_exclusive_price:
            if self.user_exclusive_price.item != self.item:
                errors['user_exclusive_price'] = "User exclusive price must correspond to the selected item."
            elif self.user_exclusive_price.user != self.cart.user:
                errors['user_exclusive_price'] = "User exclusive price must correspond to the cart's user."

        if errors:
            raise ValidationError(errors)

    def subtotal(self):
        if not self.total_cost or not self.quantity:
            return Decimal('0.00')
        return self.total_cost.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.item} in cart {self.cart} ({self.quantity} {self.unit_type})"

class Order(models.Model):
    """
    Represents a user's order with items, shipping, and payment details.
    """
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    )
    PAYMENT_STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='orders')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    shipping_address = models.TextField()
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    payment_method = models.CharField(max_length=100, blank=True)
    transaction_id = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['created_at']),
        ]
        verbose_name = 'order'
        verbose_name_plural = 'orders'

    def clean(self):
        errors = {}
        if self.total_amount < 0:
            errors['total_amount'] = "Total amount cannot be negative."
        elif self.payment_status == 'completed':
            if not self.payment_method:
                errors['payment_method'] = "Payment method is required when payment status is 'Completed'."
            elif not self.transaction_id:
                errors['transaction_id'] = "Transaction ID is required when payment status is 'Completed'."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Order {self.id} by {self.user.email} ({self.status})"

class OrderItem(models.Model):
    """
    Represents an item in an order with quantity, pricing tier, and unit type.
    """
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name='order_items')
    pricing_tier = models.ForeignKey(PricingTier, on_delete=models.PROTECT, related_name='order_items')
    quantity = models.PositiveIntegerField()
    unit_type = models.CharField(max_length=10, choices=(('pack', 'Pack'), ('pallet', 'Pallet')), default='pack')
    per_unit_price = models.DecimalField(max_digits=12, decimal_places=2, help_text="Price per unit from PricingTierData")
    per_pack_price = models.DecimalField(max_digits=12, decimal_places=2, help_text="Price per pack (price per unit * units per pack)")
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, help_text="Total cost before discounts (per pack price * quantity or adjusted for pallet)")
    user_exclusive_price = models.ForeignKey('UserExclusivePrice', on_delete=models.SET_NULL, null=True, blank=True, related_name='orderitem_items')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['order', 'item']),
            models.Index(fields=['pricing_tier']),
            models.Index(fields=['created_at']),
        ]
        verbose_name = 'order item'
        verbose_name_plural = 'order items'

    @property
    def total_units(self):
        if not self.item or not self.item.product_variant:
            return 0
        units_per_pack = self.item.product_variant.units_per_pack
        units_per_pallet = self.item.product_variant.units_per_pallet
        if self.unit_type == 'pack':
            return self.quantity * units_per_pack
        else:
            return self.quantity * units_per_pallet

    def clean(self):
        errors = {}
        if not self.item:
            errors['item'] = "Please select an item for this order entry."
        elif not self.pricing_tier:
            errors['pricing_tier'] = "Please select a pricing tier for this order entry."
        elif self.quantity <= 0:
            errors['quantity'] = "Quantity must be a positive number."

        if self.item and self.pricing_tier:
            if self.pricing_tier.product_variant != self.item.product_variant:
                errors['pricing_tier'] = "Pricing tier must belong to the same product variant as the item."
            elif self.item.product_variant.show_units_per == 'pack' and self.unit_type == 'pallet':
                errors['unit_type'] = "This item only supports pack pricing, not pallet pricing."

            total_units = self.total_units
            units_per_pack = self.item.product_variant.units_per_pack
            units_per_pallet = self.item.product_variant.units_per_pallet

            if self.unit_type == 'pack':
                if self.pricing_tier.tier_type == 'pallet':
                    pass
                elif self.quantity < self.pricing_tier.range_start:
                    errors['quantity'] = (
                        f"Quantity {self.quantity} is below the pricing tier range "
                        f"{self.pricing_tier.range_start}-{'+' if self.pricing_tier.no_end_range else self.pricing_tier.range_end}."
                    )
                elif not self.pricing_tier.no_end_range and self.quantity > self.pricing_tier.range_end:
                    errors['quantity'] = (
                        f"Quantity {self.quantity} exceeds the pricing tier range "
                        f"{self.pricing_tier.range_start}-{self.pricing_tier.range_end}."
                    )
            else:
                if self.pricing_tier.tier_type != 'pallet':
                    errors['pricing_tier'] = "Pricing tier must be 'Pallet' when unit type is 'Pallet'."
                elif self.quantity < self.pricing_tier.range_start:
                    errors['quantity'] = (
                        f"Pallet quantity {self.quantity} is below the pricing tier range "
                        f"{self.pricing_tier.range_start}-{'+' if self.pricing_tier.no_end_range else self.pricing_tier.range_end}."
                    )
                elif not self.pricing_tier.no_end_range and self.quantity > self.pricing_tier.range_end:
                    errors['quantity'] = (
                        f"Pallet quantity {self.quantity} exceeds the pricing tier range "
                        f"{self.pricing_tier.range_start}-{self.pricing_tier.range_end}."
                    )

            pricing_data = PricingTierData.objects.filter(pricing_tier=self.pricing_tier, item=self.item).first()
            if not pricing_data:
                errors['pricing_tier'] = "No pricing data found for this item and pricing tier."
            else:
                expected_per_unit_price = pricing_data.price
                expected_per_pack_price = expected_per_unit_price * Decimal(units_per_pack)
                
                if self.per_unit_price != expected_per_unit_price:
                    errors['per_unit_price'] = (
                        f"Per unit price {self.per_unit_price} does not match the expected price {expected_per_unit_price}."
                    )
                elif self.per_pack_price != expected_per_pack_price:
                    errors['per_pack_price'] = (
                        f"Per pack price {self.per_pack_price} does not match the expected price {expected_per_pack_price}."
                    )
                else:
                    if self.unit_type == 'pack':
                        if self.pricing_tier.tier_type == 'pack':
                            expected_total_cost = expected_per_pack_price * Decimal(self.quantity)
                        else:
                            total_units = Decimal(self.quantity) * Decimal(units_per_pack)
                            equivalent_pallet_quantity = total_units / Decimal(units_per_pallet)
                            expected_total_cost = equivalent_pallet_quantity * expected_per_pack_price * Decimal(units_per_pallet) / Decimal(units_per_pack)
                    else:
                        total_units = Decimal(self.quantity) * Decimal(units_per_pallet)
                        equivalent_pack_quantity = total_units / Decimal(units_per_pack)
                        expected_total_cost = equivalent_pack_quantity * expected_per_pack_price
                    
                    expected_total_cost = expected_total_cost.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    if self.total_cost != expected_total_cost:
                        errors['total_cost'] = (
                            f"Total cost {self.total_cost} does not match the expected total cost {expected_total_cost}."
                        )

        if self.item and self.item.track_inventory:
            total_units = self.total_units
            if self.item.stock is None or total_units > self.item.stock:
                errors['quantity'] = (
                    f"Insufficient stock for {self.item.sku}. Available: {self.item.stock or 0} units, Required: {total_units} units."
                )

        if self.user_exclusive_price:
            if self.user_exclusive_price.item != self.item:
                errors['user_exclusive_price'] = "User exclusive price must correspond to the selected item."
            elif self.user_exclusive_price.user != self.order.user:
                errors['user_exclusive_price'] = "User exclusive price must correspond to the order's user."

        if errors:
            raise ValidationError(errors)

    def subtotal(self):
        if not self.total_cost or not self.quantity:
            return Decimal('0.00')
        discount_percentage = self.user_exclusive_price.discount_percentage if self.user_exclusive_price else Decimal('0.00')
        discount = discount_percentage / Decimal('100.00')
        discounted_subtotal = self.total_cost * (Decimal('1.00') - discount)
        return discounted_subtotal.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.item} in order {self.order} ({self.quantity} {self.unit_type})"