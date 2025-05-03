from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from ckeditor.fields import RichTextField
from django.utils.text import slugify
from django.core.validators import MinValueValidator
from decimal import Decimal, ROUND_HALF_UP
from django.db.models.signals import post_save
from django.dispatch import receiver

class Category(models.Model):
    """
    Represents a product category with a name, slug, description, and images.
    """
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True, help_text="URL-friendly identifier, auto-generated if blank")
    description = RichTextField(blank=True)
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
            raise ValidationError("Please provide a name for the category.")

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
    description = RichTextField()
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
        if not self.name:
            raise ValidationError("Please provide a name for the product.")
        if not self.description:
            raise ValidationError("Please provide a description for the product.")
        if not self.category:
            raise ValidationError("Please select a category for the product.")

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
        if not self.image:
            raise ValidationError("Please upload an image for the product.")

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
        ('pack', 'Pack Only'),
        ('pallet', 'Pallet Only'),
        ('both', 'Both Pack and Pallet'),
    )

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='product_variants')
    name = models.CharField(max_length=255)
    units_per_pack = models.PositiveIntegerField(default=1, help_text="Number of units per pack")
    units_per_pallet = models.PositiveIntegerField(default=1, help_text="Number of units per pallet")
    show_units_per = models.CharField(max_length=10, choices=SHOW_UNITS_PER_CHOICES, default='pack')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['product', 'name']),
            models.Index(fields=['created_at']),
        ]
        verbose_name = 'product variant'
        verbose_name_plural = 'product variants'

    def clean(self):
        if not self.name:
            raise ValidationError("Please provide a name for the product variant.")
        if self.units_per_pack <= 0:
            raise ValidationError("Please provide a positive number for units per pack.")
        if self.units_per_pallet <= 0:
            raise ValidationError("Please provide a positive number for units per pallet.")
        if not self.product:
            raise ValidationError("Please select a product for the variant.")

    def validate_pricing_tiers(self):
        pricing_tiers = self.pricing_tiers.all() if self.pk else []
        if not pricing_tiers:
            raise ValidationError("Please add at least one pricing tier for this product variant.")

        pack_tiers = [tier for tier in pricing_tiers if tier.tier_type == 'pack']
        pallet_tiers = [tier for tier in pricing_tiers if tier.tier_type == 'pallet']

        if self.show_units_per == 'pack':
            if not pack_tiers:
                raise ValidationError("Please add at least one 'pack' pricing tier when 'Show Units Per' is set to 'Pack Only'.")
            if pallet_tiers:
                raise ValidationError("Pallet pricing tiers are not allowed when 'Show Units Per' is set to 'Pack Only'.")
            pack_no_end = [tier for tier in pack_tiers if tier.no_end_range]
            if len(pack_no_end) != 1:
                raise ValidationError("Please ensure exactly one 'pack' pricing tier has 'No End Range' checked.")
            for tier in pack_tiers:
                if not tier.no_end_range and tier.range_end is None:
                    raise ValidationError("Please specify a range end for non-'No End Range' pack tiers.")
        elif self.show_units_per == 'pallet':
            if not pallet_tiers:
                raise ValidationError("Please add at least one 'pallet' pricing tier when 'Show Units Per' is set to 'Pallet Only'.")
            if pack_tiers:
                raise ValidationError("Pack pricing tiers are not allowed when 'Show Units Per' is set to 'Pallet Only'.")
            pallet_no_end = [tier for tier in pallet_tiers if tier.no_end_range]
            if len(pallet_no_end) != 1:
                raise ValidationError("Please ensure exactly one 'pallet' pricing tier has 'No End Range' checked.")
            for tier in pallet_tiers:
                if not tier.no_end_range and tier.range_end is None:
                    raise ValidationError("Please specify a range end for non-'No End Range' pallet tiers.")
        elif self.show_units_per == 'both':
            if not pack_tiers:
                raise ValidationError("Please add at least one 'pack' pricing tier when 'Show Units Per' is set to 'Both Pack and Pallet'.")
            if not pallet_tiers:
                raise ValidationError("Please add at least one 'pallet' pricing tier when 'Show Units Per' is set to 'Both Pack and Pallet'.")
            pack_no_end = [tier for tier in pack_tiers if tier.no_end_range]
            pallet_no_end = [tier for tier in pallet_tiers if tier.no_end_range]
            if len(pack_no_end) != 1 or len(pallet_no_end) != 1:
                raise ValidationError("Please ensure exactly one 'pack' and one 'pallet' pricing tier have 'No End Range' checked.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        self.validate_pricing_tiers()

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
        if self.range_start is None or self.range_start <= 0:
            raise ValidationError("Please provide a positive number for the range start.")
        if self.no_end_range and self.range_end is not None:
            raise ValidationError("Please leave the range end blank when 'No End Range' is checked.")
        if not self.no_end_range and self.range_end is None:
            raise ValidationError("Please provide a range end when 'No End Range' is not checked.")
        if not self.no_end_range and self.range_end <= self.range_start:
            raise ValidationError("The range end must be greater than the range start.")
        if not self.product_variant:
            raise ValidationError("Please select a product variant for this pricing tier.")

        # Check for pack tier if creating a pallet tier
        if self.tier_type == 'pallet' and self.product_variant and self.product_variant.show_units_per != 'pallet':
            existing_pack_tiers = PricingTier.objects.filter(
                product_variant=self.product_variant,
                tier_type='pack'
            ).exclude(id=self.id)
            if not existing_pack_tiers.exists():
                raise ValidationError("You must create at least one 'pack' pricing tier before adding a 'pallet' pricing tier, unless 'Show Units Per' is set to 'Pallet Only'.")

        # Check for overlapping ranges
        existing_tiers = PricingTier.objects.filter(
            product_variant=self.product_variant,
            tier_type=self.tier_type
        ).exclude(id=self.id)
        for tier in existing_tiers:
            current_end = float('inf') if self.no_end_range else self.range_end
            tier_end = float('inf') if tier.no_end_range else tier.range_end
            if self.range_start <= tier_end and current_end >= tier.range_start:
                raise ValidationError(
                    f"The range {self.range_start}-{'+' if self.no_end_range else self.range_end} overlaps with "
                    f"existing range {tier.range_start}-{'+' if tier.no_end_range else tier.range_end} for {self.tier_type}."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        range_str = f"{self.range_start}-" + ("+" if self.no_end_range else str(self.range_end))
        return f"{self.product_variant} - {self.tier_type} - {range_str}"

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
        if self.price is None or self.price <= 0:
            raise ValidationError("Please provide a positive price.")
        if self.pricing_tier.product_variant != self.item.product_variant:
            raise ValidationError("The pricing tier must belong to the same product variant as the item.")
        if not self.item:
            raise ValidationError("Please select an item for this pricing data.")
        if not self.pricing_tier:
            raise ValidationError("Please select a pricing tier for this pricing data.")

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
        ('price', 'Price'),
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
        if not self.name:
            raise ValidationError("Please provide a name for the table field.")
        if not self.field_type:
            raise ValidationError("Please select a field type for the table field.")
        if not self.product_variant:
            raise ValidationError("Please select a product variant for the table field.")
        if self.name.lower() in self.RESERVED_NAMES:
            raise ValidationError(f"The field name '{self.name}' is reserved and cannot be used.")

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

    product_variant = models.ForeignKey('ProductVariant', on_delete=models.CASCADE, related_name='items')
    sku = models.CharField(max_length=100, unique=True)
    is_physical_product = models.BooleanField(default=False)
    weight = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    weight_unit = models.CharField(max_length=2, choices=WEIGHT_UNIT_CHOICES, blank=True, null=True)
    track_inventory = models.BooleanField(default=False)
    stock = models.IntegerField(blank=True, null=True)
    title = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    created_at = models.DateTimeField(auto_now_add=True)
    height = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, validators=[MinValueValidator(0.0)])
    width = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, validators=[MinValueValidator(0.0)])
    length = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, validators=[MinValueValidator(0.0)])
    measurement_unit = models.CharField(max_length=2, choices=MEASUREMENT_UNIT_CHOICES, blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=['product_variant']),
            models.Index(fields=['sku']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]
        verbose_name = 'item'
        verbose_name_plural = 'items'

    def clean(self):
        if not self.sku:
            raise ValidationError("Please provide a SKU for the item.")
        if not self.product_variant:
            raise ValidationError("Please select a product variant for the item.")
        if self.is_physical_product:
            if self.weight is None or self.weight <= 0:
                raise ValidationError("Please provide a positive weight for a physical product.")
            if not self.weight_unit:
                raise ValidationError("Please select a weight unit for a physical product.")
        else:
            self.weight = None
            self.weight_unit = None
        if self.track_inventory:
            if self.stock is None or self.stock < 0:
                raise ValidationError("Please provide a non-negative stock quantity when tracking inventory.")
            if not self.title:
                raise ValidationError("Please provide a title when tracking inventory.")
        else:
            self.stock = None
            self.title = None

        # Category-based validation for dimensions
        category_name = self.product_variant.product.category.name.lower() if self.product_variant and self.product_variant.product and self.product_variant.product.category else ''
        required_categories = ['box', 'boxes', 'postal', 'postals', 'bag', 'bags']
        if category_name in required_categories:
            if self.height is None or self.height <= 0:
                raise ValidationError("Please provide a positive height for items in categories: box, boxes, postal, postals, bag, bags.")
            if self.width is None or self.width <= 0:
                raise ValidationError("Please provide a positive width for items in categories: box, boxes, postal, postals, bag, bags.")
            if self.length is None or self.length <= 0:
                raise ValidationError("Please provide a positive length for items in categories: box, boxes, postal, postals, bag, bags.")
            if not self.measurement_unit:
                raise ValidationError("Please select a measurement unit for items in categories: box, boxes, postal, postals, bag, bags.")
            if self.measurement_unit not in ['MM', 'CM', 'IN', 'M']:
                raise ValidationError("Please select a valid measurement unit (MM, CM, IN, M).")
        else:
            self.height = None
            self.width = None
            self.length = None
            self.measurement_unit = None

        # Validate PricingTierData entries
        if self.pk:  # Only validate if item is being saved/updated
            pricing_tiers = self.product_variant.pricing_tiers.all()
            existing_pricing_data = set(self.pricing_tier_data.values_list('pricing_tier_id', flat=True))
            missing_tiers = [tier for tier in pricing_tiers if tier.id not in existing_pricing_data]
            if missing_tiers:
                missing_tier_names = [f"{tier.tier_type} ({tier.range_start}-{'+' if tier.no_end_range else tier.range_end})" for tier in missing_tiers]
                raise ValidationError(
                    f"Please provide pricing data for the following pricing tiers: {', '.join(missing_tier_names)}."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

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
        if not self.image:
            raise ValidationError("Please upload an image for the item.")
        if not self.item:
            raise ValidationError("Please select an item for this image.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Image for {self.item}"

class ItemData(models.Model):
    """
    Stores additional data for an item based on table fields (e.g., text, number, image, price).
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
        if not self.field:
            raise ValidationError("Please select a table field for this item data.")
        if not self.item:
            raise ValidationError("Please select an item for this item data.")

        if self.value_text == '':
            self.value_text = None
        if self.value_number == '':
            self.value_number = None
        if self.value_image == '':
            self.value_image = None

        if self.field.field_type == 'text':
            if self.value_text is None:
                raise ValidationError(f"Please provide a value for the text field '{self.field.name}'.")
            if self.value_number is not None or self.value_image:
                raise ValidationError(f"The field '{self.field.name}' only accepts text values.")
        elif self.field.field_type == 'number':
            if self.value_number is None:
                raise ValidationError(f"Please provide a number for the field '{self.field.name}'.")
            if self.value_text is not None or self.value_image:
                raise ValidationError(f"The field '{self.field.name}' only accepts number values.")
        elif self.field.field_type == 'price':
            if self.value_number is None or self.value_number < 0:
                raise ValidationError(f"Please provide a non-negative price for the field '{self.field.name}'.")
            if self.value_text is not None or self.value_image:
                raise ValidationError(f"The field '{self.field.name}' only accepts price values.")
        elif self.field.field_type == 'image':
            if not self.value_image:
                raise ValidationError(f"Please upload an image for the field '{self.field.name}'.")
            if self.value_text is not None or self.value_number is not None:
                raise ValidationError(f"The field '{self.field.name}' only accepts image values.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        if self.field.field_type == 'image' and self.value_image:
            return f"{self.item} - {self.field.name}: {self.value_image.url}"
        elif self.field.field_type == 'price':
            return f"{self.item} - {self.field.name}: ${self.value_number}"
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
        if self.discount_percentage is None or self.discount_percentage < 0 or self.discount_percentage > 100:
            raise ValidationError("Please provide a discount percentage between 0 and 100.")
        if not self.user:
            raise ValidationError("Please select a user for this exclusive price.")
        if not self.item:
            raise ValidationError("Please select an item for this exclusive price.")

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

    class Meta:
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['created_at']),
        ]
        verbose_name = 'cart'
        verbose_name_plural = 'carts'

    def calculate_total(self):
        """Calculate the total cart amount, including discounts."""
        total = Decimal('0.00')
        for item in self.items.all():
            total += item.subtotal()
        return total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def __str__(self):
        return f"Cart for {self.user.email}"

    @classmethod
    def get_or_create_cart(cls, user):
        """Safely retrieve or create a cart for the given user."""
        cart, created = cls.objects.get_or_create(user=user)
        return cart, created

# Signal to create a cart when a user is created
@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_cart(sender, instance, created, **kwargs):
    if created:
        Cart.objects.get_or_create(user=instance)

class CartItem(models.Model):
    """
    Represents an item in a cart with quantity, pricing tier, and unit type.
    """
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name='cart_items')
    pricing_tier = models.ForeignKey(PricingTier, on_delete=models.PROTECT, related_name='cart_items')
    quantity = models.PositiveIntegerField()
    unit_type = models.CharField(max_length=10, choices=(('pack', 'Pack'), ('pallet', 'Pallet')), default='pack')
    per_unit_price = models.DecimalField(max_digits=12, decimal_places=2, help_text="Price per unit from PricingTierData")
    per_pack_price = models.DecimalField(max_digits=12, decimal_places=2, help_text="Price per pack (price per unit * units per pack)")
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, help_text="Total cost before discounts (per pack price * quantity or adjusted for pallet)")
    user_exclusive_price = models.ForeignKey('UserExclusivePrice', on_delete=models.SET_NULL, null=True, blank=True, related_name='cartitem_items')
    created_at = models.DateTimeField(auto_now_add=True)

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
        """Calculate the total number of units based on quantity and unit type."""
        if not self.item or not self.item.product_variant:
            return 0
        units_per_pack = self.item.product_variant.units_per_pack
        units_per_pallet = self.item.product_variant.units_per_pallet
        if self.unit_type == 'pack':
            return self.quantity * units_per_pack
        else:  # pallet
            return self.quantity * units_per_pallet

    def clean(self):
        if self.quantity <= 0:
            raise ValidationError("Please provide a positive quantity.")
        if not self.item:
            raise ValidationError("Please select an item for this cart entry.")
        if not self.pricing_tier:
            raise ValidationError("Please select a pricing tier for this cart entry.")
        if self.pricing_tier.product_variant != self.item.product_variant:
            raise ValidationError("The pricing tier must belong to the same product variant as the item.")
        if self.item.product_variant.show_units_per == 'pack' and self.unit_type == 'pallet':
            raise ValidationError("This item only supports pack pricing, not pallet pricing.")
        if self.item.product_variant.show_units_per == 'pallet' and self.unit_type == 'pack':
            raise ValidationError("This item only supports pallet pricing, not pack pricing.")

        # Calculate total units
        total_units = self.total_units
        units_per_pack = self.item.product_variant.units_per_pack
        units_per_pallet = self.item.product_variant.units_per_pallet

        # Validate quantity against pricing tier range based on unit type
        if self.unit_type == 'pack':
            if self.pricing_tier.tier_type == 'pallet':
                # Allow pallet pricing tier with pack unit type, convert quantity to equivalent packs
                pass
            else:  # pack tier
                if not self.pricing_tier.no_end_range and self.quantity > self.pricing_tier.range_end:
                    raise ValidationError(
                        f"The quantity {self.quantity} exceeds the pricing tier range "
                        f"{self.pricing_tier.range_start}-{self.pricing_tier.range_end}."
                    )
                if self.quantity < self.pricing_tier.range_start:
                    raise ValidationError(
                        f"The quantity {self.quantity} is below the pricing tier range "
                        f"{self.pricing_tier.range_start}-{'+' if self.pricing_tier.no_end_range else self.pricing_tier.range_end}."
                    )
        else:  # pallet
            if self.pricing_tier.tier_type != 'pallet':
                raise ValidationError("Pricing tier must be of type 'pallet' when unit type is 'pallet'.")
            if not self.pricing_tier.no_end_range and self.quantity > self.pricing_tier.range_end:
                raise ValidationError(
                    f"The pallet quantity {self.quantity} exceeds the pricing tier range "
                    f"{self.pricing_tier.range_start}-{self.pricing_tier.range_end}."
                )
            if self.quantity < self.pricing_tier.range_start:
                raise ValidationError(
                    f"The pallet quantity {self.quantity} is below the pricing tier range "
                    f"{self.pricing_tier.range_start}-{'+' if self.pricing_tier.no_end_range else self.pricing_tier.range_end}."
                )

        # Validate per_unit_price, per_pack_price, and total_cost against PricingTierData
        pricing_data = PricingTierData.objects.filter(pricing_tier=self.pricing_tier, item=self.item).first()
        if not pricing_data:
            raise ValidationError("No pricing data found for this item and pricing tier.")
        expected_per_unit_price = pricing_data.price
        expected_per_pack_price = expected_per_unit_price * Decimal(units_per_pack)
        
        if self.per_unit_price != expected_per_unit_price:
            raise ValidationError(
                f"The per unit price {self.per_unit_price} does not match the expected price {expected_per_unit_price} "
                f"from PricingTierData."
            )
        
        if self.per_pack_price != expected_per_pack_price:
            raise ValidationError(
                f"The per pack price {self.per_pack_price} does not match the expected price {expected_per_pack_price} "
                f"(per unit price {expected_per_unit_price} * {units_per_pack} units per pack)."
            )
        
        # Calculate total_cost based on unit type
        if self.unit_type == 'pack':
            if self.pricing_tier.tier_type == 'pack':
                expected_total_cost = expected_per_pack_price * Decimal(self.quantity)
            else:  # pallet tier with pack unit type
                # Convert pack quantity to total units and then to equivalent pallets, but use per_pack_price for final cost
                total_units = Decimal(self.quantity) * Decimal(units_per_pack)
                equivalent_pallet_quantity = total_units / Decimal(units_per_pallet)
                expected_total_cost = equivalent_pallet_quantity * expected_per_pack_price * Decimal(units_per_pallet) / Decimal(units_per_pack)
        else:  # pallet
            # Convert pallet quantity to total units
            total_units = Decimal(self.quantity) * Decimal(units_per_pallet)
            # Convert total units to equivalent pack quantity
            equivalent_pack_quantity = total_units / Decimal(units_per_pack)
            # Calculate total cost using equivalent pack quantity and per_pack_price
            expected_total_cost = equivalent_pack_quantity * expected_per_pack_price
        
        if self.total_cost != expected_total_cost.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):
            raise ValidationError(
                f"The total cost {self.total_cost} does not match the expected total cost {expected_total_cost.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)} "
                f"for {self.unit_type} with quantity {self.quantity}."
            )

        # Validate stock
        if self.item.track_inventory:
            if self.item.stock is None or total_units > self.item.stock:
                raise ValidationError(
                    f"Insufficient stock for {self.item.sku}. Available: {self.item.stock or 0}, Required: {total_units} units."
                )

        # Validate user_exclusive_price
        if self.user_exclusive_price:
            if self.user_exclusive_price.item != self.item:
                raise ValidationError("User exclusive price must correspond to the selected item.")
            if self.user_exclusive_price.user != self.cart.user:
                raise ValidationError("User exclusive price must correspond to the cart's user.")

    def subtotal(self):
        """Calculate the subtotal for this cart item, including discounts."""
        if not self.total_cost or not self.quantity:
            return Decimal('0.00')
        # Apply discount to total_cost
        discount_percentage = self.user_exclusive_price.discount_percentage if self.user_exclusive_price else Decimal('0.00')
        discount = discount_percentage / Decimal('100.00')
        discounted_subtotal = self.total_cost * (Decimal('1.00') - discount)
        return discounted_subtotal.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

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
        if self.total_amount < 0:
            raise ValidationError("Total amount cannot be negative.")
        if self.payment_status == 'completed' and not self.payment_method:
            raise ValidationError("Payment method is required when payment status is 'completed'.")
        if self.payment_status == 'completed' and not self.transaction_id:
            raise ValidationError("Transaction ID is required when payment status is 'completed'.")

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
        """Calculate the total number of units based on quantity and unit type."""
        if not self.item or not self.item.product_variant:
            return 0
        units_per_pack = self.item.product_variant.units_per_pack
        units_per_pallet = self.item.product_variant.units_per_pallet
        if self.unit_type == 'pack':
            return self.quantity * units_per_pack
        else:  # pallet
            return self.quantity * units_per_pallet

    def clean(self):
        if self.quantity <= 0:
            raise ValidationError("Please provide a positive quantity.")
        if not self.item:
            raise ValidationError("Please select an item for this order entry.")
        if not self.pricing_tier:
            raise ValidationError("Please select a pricing tier for this order entry.")
        if self.pricing_tier.product_variant != self.item.product_variant:
            raise ValidationError("The pricing tier must belong to the same product variant as the item.")
        if self.item.product_variant.show_units_per == 'pack' and self.unit_type == 'pallet':
            raise ValidationError("This item only supports pack pricing, not pallet pricing.")
        if self.item.product_variant.show_units_per == 'pallet' and self.unit_type == 'pack':
            raise ValidationError("This item only supports pallet pricing, not pack pricing.")

        # Calculate total units
        total_units = self.total_units
        units_per_pack = self.item.product_variant.units_per_pack
        units_per_pallet = self.item.product_variant.units_per_pallet

        # Validate quantity against pricing tier range based on unit type
        if self.unit_type == 'pack':
            if self.pricing_tier.tier_type == 'pallet':
                # Allow pallet pricing tier with pack unit type, convert quantity to equivalent packs
                pass
            else:  # pack tier
                if not self.pricing_tier.no_end_range and self.quantity > self.pricing_tier.range_end:
                    raise ValidationError(
                        f"The quantity {self.quantity} exceeds the pricing tier range "
                        f"{self.pricing_tier.range_start}-{self.pricing_tier.range_end}."
                    )
                if self.quantity < self.pricing_tier.range_start:
                    raise ValidationError(
                        f"The quantity {self.quantity} is below the pricing tier range "
                        f"{self.pricing_tier.range_start}-{'+' if self.pricing_tier.no_end_range else self.pricing_tier.range_end}."
                    )
        else:  # pallet
            if self.pricing_tier.tier_type != 'pallet':
                raise ValidationError("Pricing tier must be of type 'pallet' when unit type is 'pallet'.")
            if not self.pricing_tier.no_end_range and self.quantity > self.pricing_tier.range_end:
                raise ValidationError(
                    f"The pallet quantity {self.quantity} exceeds the pricing tier range "
                    f"{self.pricing_tier.range_start}-{self.pricing_tier.range_end}."
                )
            if self.quantity < self.pricing_tier.range_start:
                raise ValidationError(
                    f"The pallet quantity {self.quantity} is below the pricing tier range "
                    f"{self.pricing_tier.range_start}-{'+' if self.pricing_tier.no_end_range else self.pricing_tier.range_end}."
                )

        # Validate per_unit_price, per_pack_price, and total_cost against PricingTierData
        pricing_data = PricingTierData.objects.filter(pricing_tier=self.pricing_tier, item=self.item).first()
        if not pricing_data:
            raise ValidationError("No pricing data found for this item and pricing tier.")
        expected_per_unit_price = pricing_data.price
        expected_per_pack_price = expected_per_unit_price * Decimal(units_per_pack)
        
        if self.per_unit_price != expected_per_unit_price:
            raise ValidationError(
                f"The per unit price {self.per_unit_price} does not match the expected price {expected_per_unit_price} "
                f"from PricingTierData."
            )
        
        if self.per_pack_price != expected_per_pack_price:
            raise ValidationError(
                f"The per pack price {self.per_pack_price} does not match the expected price {expected_per_pack_price} "
                f"(per unit price {expected_per_unit_price} * {units_per_pack} units per pack)."
            )
        
        # Calculate total_cost based on unit type
        if self.unit_type == 'pack':
            if self.pricing_tier.tier_type == 'pack':
                expected_total_cost = expected_per_pack_price * Decimal(self.quantity)
            else:  # pallet tier with pack unit type
                # Convert pack quantity to total units and then to equivalent pallets, but use per_pack_price for final cost
                total_units = Decimal(self.quantity) * Decimal(units_per_pack)
                equivalent_pallet_quantity = total_units / Decimal(units_per_pallet)
                expected_total_cost = equivalent_pallet_quantity * expected_per_pack_price * Decimal(units_per_pallet) / Decimal(units_per_pack)
        else:  # pallet
            # Convert pallet quantity to total units
            total_units = Decimal(self.quantity) * Decimal(units_per_pallet)
            # Convert total units to equivalent pack quantity
            equivalent_pack_quantity = total_units / Decimal(units_per_pack)
            # Calculate total cost using equivalent pack quantity and per_pack_price
            expected_total_cost = equivalent_pack_quantity * expected_per_pack_price
        
        if self.total_cost != expected_total_cost.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):
            raise ValidationError(
                f"The total cost {self.total_cost} does not match the expected total cost {expected_total_cost.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)} "
                f"for {self.unit_type} with quantity {self.quantity}."
            )

        # Validate stock
        if self.item.track_inventory:
            if self.item.stock is None or total_units > self.item.stock:
                raise ValidationError(
                    f"Insufficient stock for {self.item.sku}. Available: {self.item.stock or 0}, Required: {total_units} units."
                )

        # Validate user_exclusive_price
        if self.user_exclusive_price:
            if self.user_exclusive_price.item != self.item:
                raise ValidationError("User exclusive price must correspond to the selected item.")
            if self.user_exclusive_price.user != self.order.user:
                raise ValidationError("User exclusive price must correspond to the order's user.")

    def subtotal(self):
        """Calculate the subtotal for this order item, including discounts."""
        if not self.total_cost or not self.quantity:
            return Decimal('0.00')
        # Apply discount to total_cost
        discount_percentage = self.user_exclusive_price.discount_percentage if self.user_exclusive_price else Decimal('0.00')
        discount = discount_percentage / Decimal('100.00')
        discounted_subtotal = self.total_cost * (Decimal('1.00') - discount)
        return discounted_subtotal.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.item} in order {self.order} ({self.quantity} {self.unit_type})"