import logging
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django_ckeditor_5.fields import CKEditor5Field
from django.utils.text import slugify
from django.core.validators import MinValueValidator
from decimal import Decimal, ROUND_HALF_UP
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.db import transaction
from django.core.files.base import ContentFile
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.platypus.flowables import Flowable
import uuid
from datetime import timedelta
from io import BytesIO
from phonenumber_field.modelfields import PhoneNumberField
from backend_praco.utils import send_email
from django.db.models import Sum 

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
    Represents a variant of a product with specific attributes like pack units.
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
    # units_per_pack = models.PositiveIntegerField(default=6, help_text="Number of units per pack")
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
        # elif self.units_per_pack <= 0:
            # errors['units_per_pack'] = "Units per pack must be a positive number."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.name} - {self.name}"

class PricingTier(models.Model):
    """
    Defines pricing tiers for product variants based on quantity ranges for packs or weight-based for pallets.
    """
    TIER_TYPES = (
        ('pack', 'Pack'),
        ('pallet', 'Pallet'),
    )

    product_variant = models.ForeignKey('ProductVariant', on_delete=models.CASCADE, related_name='pricing_tiers')
    tier_type = models.CharField(max_length=10, choices=TIER_TYPES)
    range_start = models.PositiveIntegerField(default=1, blank=True, help_text="Start of range for pack tiers; ignored for pallet tiers")
    range_end = models.PositiveIntegerField(null=True, blank=True, help_text="End of range for pack tiers; ignored for pallet tiers")
    no_end_range = models.BooleanField(default=False, help_text="Check if this pack tier has no end range; ignored for pallet tiers")
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

        # Validate tier_type against product_variant.show_units_per
        if self.product_variant:
            if self.product_variant.show_units_per == 'pack' and self.tier_type != 'pack':
                errors['tier_type'] = "Only 'Pack' tier type is allowed when the variant is set to show only pack."
            elif self.product_variant.show_units_per == 'both' and self.tier_type not in ['pack', 'pallet']:
                errors['tier_type'] = "Tier type must be either 'Pack' or 'Pallet' when showing both."

        # Validate tiers
        if self.product_variant:
            # Fetch existing tiers except the current one (for updates)
            existing_tiers = PricingTier.objects.filter(
                product_variant=self.product_variant,
                tier_type=self.tier_type
            ).exclude(id=self.id if self.id else None).order_by('range_start')

            # Validate pallet tiers
            if self.tier_type == 'pallet':
                if existing_tiers.exists():
                    errors['tier_type'] = "Only one pallet tier is allowed per product variant."
            # Validate pack tiers
            elif self.tier_type == 'pack':
                if self.range_start <= 0:
                    errors['range_start'] = "Range start must be a positive number."
                elif self.no_end_range and self.range_end is not None:
                    errors['range_end'] = "Range end must be blank when 'No End Range' is checked."
                elif not self.no_end_range and self.range_end is None:
                    errors['range_end'] = "Range end is required for pack tiers unless 'No End Range' is checked."
                elif not self.no_end_range and self.range_end < self.range_start:
                    errors['range_end'] = "Range end must be equal or greater than range start for pack tiers."

                all_tiers = list(existing_tiers)
                all_tiers.append(self)
                all_tiers.sort(key=lambda x: x.range_start)

                # Check if any tier starts at 1
                has_first_tier = any(tier.range_start == 1 for tier in existing_tiers)
                
                # If no existing tier starts at 1, this tier must start at 1
                if not has_first_tier and self.range_start != 1:
                    errors['range_start'] = "The first pack tier must start from 1."

                # Check for overlaps, gaps, and ensure no_end_range is last
                for i in range(len(all_tiers) - 1):
                    current = all_tiers[i]
                    next_tier = all_tiers[i + 1]
                    current_end = float('inf') if current.no_end_range else (current.range_end if current.range_end is not None else float('inf'))
                    next_end = float('inf') if next_tier.no_end_range else (next_tier.range_end if next_tier.range_end is not None else float('inf'))
                    
                    # Check for overlaps
                    if current.range_start <= next_end and current_end >= next_tier.range_start:
                        errors['range_start'] = (
                            f"Range {current.range_start}-{'+' if current.no_end_range else current.range_end} overlaps with "
                            f"range {next_tier.range_start}-{'+' if next_tier.no_end_range else next_tier.range_end} for {self.tier_type}."
                        )
                        break
                    
                    # Check for gaps and sequential order
                    if not current.no_end_range:
                        current_end = current.range_end if current.range_end is not None else float('inf')
                        if next_tier.range_start != current_end + 1:
                            errors['range_start'] = (
                                f"Range {current.range_start}-{'+' if current.no_end_range else current.range_end} creates a gap or is not sequential "
                                f"with range {next_tier.range_start}-{'+' if next_tier.no_end_range else next_tier.range_end} for {self.tier_type}. "
                                "Ensure ranges are sequential with no gaps."
                            )
                            break
                
                # Ensure no_end_range is the last tier
                for i in range(len(all_tiers) - 1):
                    current = all_tiers[i]
                    if current.no_end_range:
                        next_tier = all_tiers[i + 1]
                        errors['range_start'] = (
                            f"A tier with 'No End Range' checked must be the last tier. Cannot add {next_tier.range_start}-"
                            f"{'+' if next_tier.no_end_range else next_tier.range_end} after {current.range_start}+ for {self.tier_type}."
                        )
                        break

        if errors:
            raise ValidationError(errors)

    @classmethod
    def get_appropriate_tier(cls, product_variant, quantity, tier_type='pack'):
        """
        Find the best pricing tier for a given quantity and tier type.
        Returns the most appropriate pricing tier based on the quantity.
        """
        tiers = cls.objects.filter(
            product_variant=product_variant,
            tier_type=tier_type
        ).order_by('range_start')

        if not tiers.exists():
            return None

        # For pallet tiers, just return the single pallet tier
        if tier_type == 'pallet':
            return tiers.first()

        # For pack tiers, find the best matching tier
        for tier in tiers:
            if quantity >= tier.range_start and (
                tier.no_end_range or (tier.range_end and quantity <= tier.range_end)
            ):
                return tier

        # If no exact match found, return the highest tier that's below the quantity
        # This is useful when quantity exceeds all tier ranges
        return tiers.last()

    def check_pricing_tiers_conditions(self):
        """
        Check if the pricing tiers for the associated ProductVariant meet the conditions to set status='active'.
        """
        try:
            pricing_tiers = self.product_variant.pricing_tiers.all()
            if not hasattr(pricing_tiers, '__iter__'):
                return False
            pack_tiers = sorted([tier for tier in pricing_tiers if tier.tier_type == 'pack'], 
                              key=lambda x: x.range_start)
            pallet_tiers = [tier for tier in pricing_tiers if tier.tier_type == 'pallet']

            # Validate show_units_per settings
            if self.product_variant.show_units_per == 'pack':
                if not pack_tiers or pallet_tiers:
                    return False
                pack_no_end = [tier for tier in pack_tiers if tier.no_end_range]
                if len(pack_no_end) != 1:
                    return False
                if pack_tiers and pack_tiers[0].range_start != 1:
                    return False
                for tier in pack_tiers:
                    if not tier.no_end_range and tier.range_end is None:
                        return False
                for i in range(len(pack_tiers) - 1):
                    current = pack_tiers[i]
                    next_tier = pack_tiers[i + 1]
                    if current.no_end_range:
                        return False  # No tiers should exist after no_end_range
                    current_end = current.range_end if current.range_end is not None else float('inf')
                    if next_tier.range_start != current_end + 1:
                        return False
            elif self.product_variant.show_units_per == 'both':
                if not pack_tiers or not pallet_tiers:
                    return False
                pack_no_end = [tier for tier in pack_tiers if tier.no_end_range]
                if len(pack_no_end) != 1:
                    return False
                if len(pallet_tiers) > 1:
                    return False
                if pack_tiers and pack_tiers[0].range_start != 1:
                    return False
                for tier in pack_tiers:
                    if not tier.no_end_range and tier.range_end is None:
                        return False
                for i in range(len(pack_tiers) - 1):
                    current = pack_tiers[i]
                    next_tier = pack_tiers[i + 1]
                    if current.no_end_range:
                        return False  # No tiers should exist after no_end_range
                    current_end = current.range_end if current.range_end is not None else float('inf')
                    if next_tier.range_start != current_end + 1:
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
        if self.tier_type == 'pallet':
            return f"{self.product_variant} - {self.tier_type}"
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
    price = models.DecimalField(max_digits=12, decimal_places=8, help_text="Price per unit")
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
    weight = models.DecimalField(max_digits=10, decimal_places=8, blank=True, null=True)
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
    units_per_pack = models.PositiveIntegerField(validators=[MinValueValidator(1)], default=1)

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
            # Validate is_physical_product when show_units_per is 'both'
            if self.product_variant.show_units_per == 'both' and not self.is_physical_product:
                errors['is_physical_product'] = "Item must be a physical product when product variant show units per is set to 'both'."

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
                if self.length is None or self.length < 0:
                    errors['length'] = "Length must be a positive number for this category."
                if not self.measurement_unit:
                    errors['measurement_unit'] = "Please select a measurement unit for this category."
                if self.measurement_unit and self.measurement_unit not in ['MM', 'CM', 'IN', 'M']:
                    errors['measurement_unit'] = "Please select a valid measurement unit (MM, CM, IN, M)."
            else:
                # Only clear dimensions if they are not provided or invalid
                if not all([self.height, self.width, self.length, self.measurement_unit]) or \
                   any([self.height is not None and self.height <= 0,
                        self.width is not None and self.width <= 0,
                        self.length is not None and self.length <= 0,
                        self.measurement_unit and self.measurement_unit not in ['MM', 'CM', 'IN', 'M']]):
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
                # Validate that stock is a multiple of units_per_pack
                if self.stock is not None and self.units_per_pack > 0 and self.stock % self.units_per_pack != 0:
                    errors['stock'] = f"Stock must be a multiple of units per pack ({self.units_per_pack}). Current stock: {self.stock}."
            else:
                self.stock = None
                # self.title = None

            if self.units_per_pack <= 0:
                errors['units_per_pack'] = "Units per pack must be a positive number."

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
            except AttributeError:
                pass

    def delete(self, *args, **kwargs):
        """Delete associated images before deleting the item."""
        try:
            for item_image in self.images.all():
                if item_image.image:
                    item_image.image.delete(save=False)
                    logger.info(f"Deleted image {item_image.image.name} for item {self.sku}")
        except Exception as e:
            logger.error(f"Error deleting images for item {self.sku}: {str(e)}")
        super().delete(*args, **kwargs)

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


class CartItem(models.Model):
    cart = models.ForeignKey('Cart', on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey('Item', on_delete=models.PROTECT, related_name='cart_items')
    pricing_tier = models.ForeignKey('PricingTier', on_delete=models.PROTECT, related_name='cart_items')
    pack_quantity = models.PositiveIntegerField()
    unit_type = models.CharField(
        max_length=10,
        choices=(('pack', 'Pack'), ('pallet', 'Pallet')),
        default='pack',
        help_text="Unit type for pricing tier selection."
    )
    user_exclusive_price = models.ForeignKey('UserExclusivePrice', on_delete=models.SET_NULL, null=True, blank=True,
                                          related_name='cartitem_items')
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

    def convert_weight_to_kg(self, weight, weight_unit):
        if weight is None or weight_unit is None:
            return Decimal('0.00000000')
        weight = Decimal(str(weight))
        if weight_unit == 'lb':
            return (weight * Decimal('0.453592')).quantize(Decimal('0.00000001'))
        elif weight_unit == 'oz':
            return (weight * Decimal('0.0283495')).quantize(Decimal('0.00000001'))
        elif weight_unit == 'g':
            return (weight * Decimal('0.001')).quantize(Decimal('0.00000001'))
        elif weight_unit == 'kg':
            return weight.quantize(Decimal('0.00000001'))
        return Decimal('0.00000000')

    @property
    def total_units(self):
        if not self.item:
            return 0
        units_per_pack = self.item.units_per_pack or 1
        total = self.pack_quantity * units_per_pack
        return total

    @property
    def total_weight_kg(self):
        if not self.item:
            return Decimal('0.00000000')
        item_weight_kg = self.convert_weight_to_kg(self.item.weight, self.item.weight_unit)
        total = (item_weight_kg * Decimal(self.total_units)).quantize(Decimal('0.00000001'))
        return total

    def get_appropriate_pricing_tier(self):
        from .models import PricingTier
        quantity = self.pack_quantity
        tier = PricingTier.get_appropriate_tier(
            product_variant=self.item.product_variant,
            quantity=quantity,
            tier_type=self.unit_type
        )
        return tier

    def clean(self):
        errors = {}
        
        if not self.item:
            errors['item'] = "Please select an item for this cart entry."
        if not self.pricing_tier:
            errors['pricing_tier'] = "Please select a pricing tier for this cart entry."
        if self.pack_quantity <= 0:
            errors['pack_quantity'] = "Pack quantity must be a positive number."

        if self.item and self.pricing_tier:
            if self.pricing_tier.product_variant != self.item.product_variant:
                errors['pricing_tier'] = "Pricing tier must belong to the same product variant as the item."
            if self.pricing_tier.tier_type != self.unit_type:
                errors['unit_type'] = f"Unit type {self.unit_type} does not match pricing tier type {self.pricing_tier.tier_type}."

            if self.pack_quantity < self.pricing_tier.range_start:
                errors['pack_quantity'] = (
                    f"Pack quantity {self.pack_quantity} is below the pricing tier range "
                    f"{self.pricing_tier.range_start}-{'+' if self.pricing_tier.no_end_range else self.pricing_tier.range_end}."
                )
            elif not self.pricing_tier.no_end_range and self.pack_quantity > self.pricing_tier.range_end:
                errors['pack_quantity'] = (
                    f"Pack quantity {self.pack_quantity} exceeds the pricing tier range "
                    f"{self.pricing_tier.range_start}-{self.pricing_tier.range_end}."
                )

            if self.item.track_inventory:
                total_units = self.total_units
                available_stock = self.item.stock
                units_per_pack = self.item.units_per_pack or 1
                
                existing_cart_units = CartItem.objects.filter(
                    cart=self.cart,
                    item=self.item
                ).exclude(pk=self.pk).aggregate(
                    total=Sum('pack_quantity') * units_per_pack
                )['total'] or 0
                
                available_for_new = max(0, available_stock - existing_cart_units)
                
                if available_stock is None or total_units > available_stock:
                    errors['pack_quantity'] = (
                        f"Insufficient stock for {self.item.sku}. "
                        f"Total available: {available_stock or 0} units, "
                        f"Already in cart: {existing_cart_units} units, "
                        f"Available for this addition: {available_for_new} units, "
                        f"Requested: {total_units} units."
                    )

        if self.user_exclusive_price:
            if self.item and self.user_exclusive_price.item != self.item:
                errors['user_exclusive_price'] = "User exclusive price must correspond to the selected item."
            if self.cart and self.user_exclusive_price.user != self.cart.user:
                errors['user_exclusive_price'] = "User exclusive price must correspond to the cart's user."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        from django.db import transaction
        
        if not self.item:
            raise ValidationError({"item": "CartItem cannot be saved without an item."})

        with transaction.atomic():
            existing_cart_item = CartItem.objects.filter(
                cart=self.cart,
                item=self.item,
                unit_type=self.unit_type
            ).exclude(pk=self.pk).first()

            if existing_cart_item:
                existing_cart_item.pack_quantity += self.pack_quantity
                existing_cart_item.pricing_tier = self.pricing_tier
                existing_cart_item.user_exclusive_price = self.user_exclusive_price
                existing_cart_item.full_clean()
                existing_cart_item.save(*args, **kwargs)
                self.pk = existing_cart_item.pk
                cart_item = existing_cart_item
            else:
                self.full_clean()
                super().save(*args, **kwargs)
                cart_item = self

            try:
                self.cart.update_cart()
                self.cart.update_pricing_tiers()
            except Exception as e:
                pass

            return cart_item

class Cart(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='cart',
        help_text="The user associated with this cart."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
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

    class Meta:
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['created_at']),
        ]
        verbose_name = 'cart'
        verbose_name_plural = 'carts'

    @classmethod
    def get_or_create_cart(cls, user):
        cart, created = cls.objects.get_or_create(user=user)
        return cart, created

    def add_or_update_item(self, item_data):
        from .models import PricingTier
        item_id = item_data['item'].id
        pack_quantity = item_data.get('pack_quantity', 0)
        unit_type = item_data.get('unit_type', 'pack')
        units_per_pack = item_data['item'].units_per_pack or 1

        with transaction.atomic():
            # Calculate total weight including the new item
            new_units = pack_quantity * units_per_pack
            new_weight = self.convert_weight_to_kg(
                item_data['item'].weight * new_units,
                item_data['item'].weight_unit
            )
            current_weight = sum(item.total_weight_kg for item in self.items.exclude(item_id=item_id))
            total_weight = current_weight + new_weight

            # Determine pricing tier type
            has_pallet_pricing = item_data['item'].product_variant.pricing_tiers.filter(
                tier_type='pallet'
            ).exists()
            target_unit_type = 'pallet' if total_weight >= Decimal('750.00000000') and has_pallet_pricing else 'pack'

            # Sum existing and new pack quantities
            existing_items = self.items.filter(item_id=item_id)
            total_pack_quantity = pack_quantity
            for existing_item in existing_items:
                total_pack_quantity += existing_item.pack_quantity
                existing_item.delete()  # Consolidate into one item

            # Find appropriate pricing tier
            new_pricing_tier = PricingTier.get_appropriate_tier(
                product_variant=item_data['item'].product_variant,
                quantity=total_pack_quantity,
                tier_type=target_unit_type
            )

            if not new_pricing_tier:
                new_pricing_tier = item_data['item'].product_variant.pricing_tiers.filter(
                    tier_type=target_unit_type
                ).order_by('-range_start').first()

            if not new_pricing_tier:
                raise ValidationError(f"No suitable {target_unit_type} pricing tier found for quantity {total_pack_quantity}.")
            
            # Validate inventory if needed
            if item_data['item'].track_inventory:
                total_units = total_pack_quantity * units_per_pack
                available_stock = item_data['item'].stock or 0
                if total_units > available_stock:
                    raise ValidationError(
                        f"Insufficient stock for {item_data['item'].sku}. "
                        f"Total available: {available_stock} units, "
                        f"Requested: {total_units} units."
                    )

            # Create new cart item with total pack quantity
            cart_item = self.items.create(
                item=item_data['item'],
                pricing_tier=new_pricing_tier,
                pack_quantity=total_pack_quantity,
                unit_type=target_unit_type,
                user_exclusive_price=item_data.get('user_exclusive_price')
            )

            self.update_pricing_tiers()
            return cart_item

    def convert_weight_to_kg(self, weight, weight_unit):
        if weight is None or weight_unit is None:
            return Decimal('0.00000000')
        weight = Decimal(str(weight))
        if weight_unit == 'lb':
            return (weight * Decimal('0.453592')).quantize(Decimal('0.00000001'))
        elif weight_unit == 'oz':
            return (weight * Decimal('0.0283495')).quantize(Decimal('0.00000001'))
        elif weight_unit == 'g':
            return (weight * Decimal('0.001')).quantize(Decimal('0.00000001'))
        elif weight_unit == 'kg':
            return weight.quantize(Decimal('0.00000001'))
        return Decimal('0.00000000')

    def calculate_subtotal(self):
        total = Decimal('0.00')
        for item in self.items.all():
            pricing_data = PricingTierData.objects.filter(pricing_tier=item.pricing_tier, item=item.item).first()
            if pricing_data and item.item:
                units_per_pack = item.item.units_per_pack or 1
                per_pack_price = pricing_data.price * Decimal(units_per_pack)
                item_subtotal = per_pack_price * Decimal(item.pack_quantity)
                if item.user_exclusive_price:
                    discount_percentage = item.user_exclusive_price.discount_percentage
                    discount = discount_percentage / Decimal('100.00')
                    item_subtotal = item_subtotal * (Decimal('1.00') - discount)
                total += item_subtotal.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def calculate_total_units_and_packs(self):
        total_units = 0
        total_packs = 0
        for item in self.items.all():
            units_per_pack = item.item.units_per_pack or 1
            total_units += item.pack_quantity * units_per_pack
            total_packs += item.pack_quantity
        return total_units, total_packs

    def calculate_total_weight(self):
        total_weight = Decimal('0.00000000')
        for item in self.items.all():
            total_weight += item.total_weight_kg
        return total_weight.quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)

    def calculate_total(self):
        subtotal = self.calculate_subtotal()
        vat_amount = (subtotal * self.vat) / Decimal('100.00')
        total = subtotal + vat_amount
        print(total, 'total')
        return total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    def update_cart(self):
        self.save()

    def update_pricing_tiers(self):
        from .models import PricingTier
        total_weight = self.calculate_total_weight()
        use_pallet_pricing = total_weight >= Decimal('750.00000000')

        with transaction.atomic():
            for item in self.items.select_for_update():
                if not item.item or not item.item.product_variant:
                    continue

                variant = item.item.product_variant
                has_pallet_pricing = variant.pricing_tiers.filter(
                    tier_type='pallet'
                ).exists()

                new_pricing_tier = None
                new_unit_type = 'pack' if not (use_pallet_pricing and has_pallet_pricing) else 'pallet'
                pack_quantity = item.pack_quantity

                tiers = variant.pricing_tiers.filter(
                    tier_type=new_unit_type
                ).order_by('range_start')

                for tier in tiers:
                    if pack_quantity >= tier.range_start and (
                        tier.no_end_range or pack_quantity <= tier.range_end
                    ):
                        new_pricing_tier = tier
                        break
                if not new_pricing_tier:
                    new_pricing_tier = tiers.last()

                if not new_pricing_tier:
                    continue

                if new_pricing_tier and (item.pricing_tier != new_pricing_tier or item.unit_type != new_unit_type):
                    item.pricing_tier = new_pricing_tier
                    item.unit_type = new_unit_type
                    item.full_clean()
                    item.save()

def update_cart_pricing_tiers(sender, instance, **kwargs):
    """
    Update pricing tiers when cart items change
    """
    if instance.cart:
        instance.cart.update_pricing_tiers()

@receiver(post_delete, sender=CartItem)
def update_cart_pricing_tiers_on_delete(sender, instance, **kwargs):
    """
    Update pricing tiers when cart items are deleted
    """
    if instance.cart:
        instance.cart.update_pricing_tiers()

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_cart(sender, instance, created, **kwargs):
    if created:
        Cart.objects.get_or_create(user=instance)


class Address(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='addresses')
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    telephone_number = PhoneNumberField()
    street = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'address'
        verbose_name_plural = 'addresses'

logger = logging.getLogger(__name__)

class HRFlowable(Flowable):
    def __init__(self, width, thickness=1, color=colors.black):
        super().__init__()
        self.width = width
        self.thickness = thickness
        self.color = color

    def wrap(self, availWidth, availHeight):
        self.width = min(self.width, availWidth)
        return (self.width, self.thickness)

    def draw(self):
        self.canv.setLineWidth(self.thickness)
        self.canv.setStrokeColor(self.color)
        self.canv.line(0, 0, self.width, 0)


class Transaction(models.Model):
    order = models.ForeignKey('Order', on_delete=models.CASCADE, related_name='transactions')
    stripe_payment_intent_id = models.CharField(max_length=100, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='gbp')
    status = models.CharField(max_length=20, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'transaction'
        verbose_name_plural = 'transactions'

    def __str__(self):
        return f"Transaction {self.stripe_payment_intent_id} for Order {self.order.id}"

# class Order(models.Model):
#     STATUS_CHOICES = (
#         ('PENDING', 'Pending'),
#         ('PROCESSING', 'Processing'),
#         ('SHIPPED', 'Shipped'),
#         ('DELIVERED', 'Delivered'),
#         ('CANCELLED', 'Cancelled'),
#         ('RETURNED', 'Returned'),
#     )
#     PAYMENT_STATUS_CHOICES = (
#         ('PENDING', 'Pending'),
#         ('COMPLETED', 'Completed'),
#         ('FAILED', 'Failed'),
#         ('REFUND', 'Refund'),
#     )
#     PAYMENT_METHOD_CHOICES = (
#         ('manual_payment', 'Manual Payment'),
#     )

#     user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
#     shipping_address = models.ForeignKey('ShippingAddress', on_delete=models.SET_NULL, null=True)
#     billing_address = models.ForeignKey('BillingAddress', on_delete=models.SET_NULL, null=True)
#     shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, editable=False)
#     vat = models.DecimalField(
#         max_digits=5,
#         decimal_places=2,
#         default=Decimal('20.00'),
#         help_text="VAT percentage (e.g., 20 for 20%)."
#     )
#     discount = models.DecimalField(
#         max_digits=5,
#         decimal_places=2,
#         default=Decimal('0.00'),
#         help_text="Discount percentage (e.g., 10 for 10%)."
#     )
#     status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
#     payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='PENDING')
#     payment_verified = models.BooleanField(default=False)
#     payment_method = models.CharField(
#         max_length=50,
#         choices=PAYMENT_METHOD_CHOICES,
#         default='manual_payment',
#         editable=False
#     )
#     transaction_id = models.CharField(max_length=100, blank=True, null=True)
#     payment_receipt = models.FileField(upload_to='receipts/', blank=True, null=True)
#     refund_transaction_id = models.CharField(max_length=100, blank=True, null=True)
#     refund_payment_receipt = models.FileField(upload_to='refund_receipts/', blank=True, null=True)
#     paid_receipt = models.FileField(upload_to='paid_receipts/', blank=True, null=True, editable=False)
#     refund_receipt = models.FileField(upload_to='refund_receipts/', blank=True, null=True, editable=False)
#     invoice = models.FileField(upload_to='invoices/', null=True, blank=True, editable=False)
#     delivery_note = models.FileField(upload_to='delivery_notes/', null=True, blank=True, editable=False)
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)

#     class Meta:
#         indexes = [
#             models.Index(fields=['user']),
#             models.Index(fields=['created_at']),
#         ]
#         verbose_name = 'order'
#         verbose_name_plural = 'orders'

#     def clean(self):
#         errors = {}
#         if self.payment_verified:
#             if not self.transaction_id:
#                 errors['transaction_id'] = 'Transaction ID is required when payment is verified.'
#             if not self.payment_receipt:
#                 errors['payment_receipt'] = 'Payment receipt is required when payment is verified.'
#             if self.payment_status in ['FAILED', 'PENDING']:
#                 errors['payment_status'] = 'Payment status must be Completed/Refunded when payment is verified.'
        
#         if self.payment_status == 'COMPLETED':
#             if not self.transaction_id:
#                 errors['transaction_id'] = 'Transaction ID is required when payment status is Completed.'
#             if not self.payment_receipt:
#                 errors['payment_receipt'] = 'Payment receipt is required when payment status is Completed.'
        
#         elif self.payment_status == 'REFUND':
#             if not self.transaction_id:
#                 errors['transaction_id'] = 'Transaction ID is required when payment status is Refunded.'
#             if not self.payment_receipt:
#                 errors['payment_receipt'] = 'Payment receipt is required when payment status is Refunded.'
#             if not self.refund_transaction_id:
#                 errors['refund_transaction_id'] = 'Refunded transaction ID is required when payment status is Refunded.'
#             if not self.refund_payment_receipt:
#                 errors['refund_payment_receipt'] = 'Refunded payment receipt is required when payment status is Refunded.'

#         for field, field_name in [(self.payment_receipt, 'payment_receipt'), (self.refund_payment_receipt, 'refund_payment_receipt')]:
#             if field:
#                 ext = field.name.lower().split('.')[-1]
#                 if ext not in ['png', 'jpg', 'jpeg', 'pdf']:
#                     errors[field_name] = 'File must be a PNG, JPG, or PDF.'

#         if errors:
#             raise ValidationError(errors)

#         if self.payment_status == 'REFUND' and not self.paid_receipt:
#             raise ValidationError({'__all__': 'Paid receipt must exist when payment status is Refunded.'})

#     def calculate_subtotal(self):
#         """Calculate the overall subtotal by summing the totals of all OrderItems after UserExclusivePrice discounts."""
#         try:
#             total = Decimal('0.00')
#             for item in self.items.all():
#                 item_subtotal = item.calculate_subtotal()
#                 total += item_subtotal
#             logger.info(f"Order {self.id} subtotal: {total}")
#             return total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
#         except Exception as e:
#             logger.error(f"Error calculating subtotal for order {self.id}: {str(e)}")
#             return Decimal('0.00')

#     def calculate_original_subtotal(self):
#         """Calculate the overall subtotal after UserExclusivePrice discounts (same as calculate_subtotal)."""
#         try:
#             total = self.calculate_subtotal()
#             logger.info(f"Order {self.id} original subtotal: {total}")
#             return total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
#         except Exception as e:
#             logger.error(f"Error calculating original subtotal for order {self.id}: {str(e)}")
#             return Decimal('0.00')

#     def calculate_total(self):
#         """
#         Calculate the overall total:
#         1. Start with overall subtotal (sum of item totals after UserExclusivePrice discounts).
#         2. Apply order-level discount.
#         3. Add VAT (e.g., 20% of discounted subtotal).
#         4. Add shipping cost.
#         """
#         try:
#             subtotal = self.calculate_subtotal()  # After UserExclusivePrice discounts
#             discount_amount = (subtotal * self.discount) / Decimal('100.00')
#             discounted_subtotal = subtotal - discount_amount
#             vat_amount = (discounted_subtotal * self.vat) / Decimal('100.00')
#             shipping_cost = Decimal(str(self.shipping_cost)).quantize(Decimal('0.01'))
#             total = (discounted_subtotal + vat_amount + shipping_cost).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
#             logger.info(f"Order {self.id} total: {total} (subtotal={subtotal}, discount={self.discount}%, vat={self.vat}%, shipping={shipping_cost})")
#             return total
#         except Exception as e:
#             logger.error(f"Error calculating total for order {self.id}: {str(e)}")
#             return Decimal('0.00')

#     def calculate_total_weight(self):
#         """Calculate the total weight of all OrderItems."""
#         try:
#             total_weight = Decimal('0.00000000')
#             for item in self.items.all():
#                 item_weight_kg = item.calculate_weight()
#                 total_units = item.total_units
#                 total_weight += item_weight_kg * Decimal(total_units)
#             logger.info(f"Order {self.id} total weight: {total_weight}")
#             return total_weight.quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)
#         except Exception as e:
#             logger.error(f"Error calculating total weight for order {self.id}: {str(e)}")
#             return Decimal('0.00000000')

#     def calculate_total_units_and_packs(self):
#         """Calculate total units and packs across all OrderItems."""
#         try:
#             total_units = 0
#             total_packs = 0
#             for item in self.items.all():
#                 units_per_pack = item.item.units_per_pack or 1
#                 total_units += item.pack_quantity * units_per_pack
#                 total_packs += item.pack_quantity
#             logger.info(f"Order {self.id} total units: {total_units}, total packs: {total_packs}")
#             return total_units, total_packs
#         except Exception as e:
#             logger.error(f"Error calculating units and packs for order {self.id}: {str(e)}")
#             return 0, 0

#     def update_order(self):
#         """Update order calculations."""
#         try:
#             self.calculate_total()
#             super().save(update_fields=['discount'])
#             logger.info(f"Updated order {self.id} calculations")
#         except Exception as e:
#             logger.error(f"Error updating order {self.id}: {str(e)}")

#     def generate_invoice_pdf(self):
#         try:
#             buffer = BytesIO()
#             doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
#             elements = []
#             styles = getSampleStyleSheet()
#             normal_style = styles['Normal']
#             normal_style.fontName = 'Helvetica'
#             normal_style.fontSize = 11
#             bold_style = ParagraphStyle(name='Bold', parent=normal_style, fontName='Helvetica-Bold')
#             title_style = ParagraphStyle(name='Title', fontName='Helvetica-Bold', fontSize=14, textColor=colors.black)
#             orange_style = ParagraphStyle(name='Orange', fontName='Helvetica-Bold', fontSize=12, textColor=HexColor('#F28C38'))
#             small_style = ParagraphStyle(name='Small', fontName='Helvetica', fontSize=8)

#             elements.append(Paragraph(f"Invoice #{self.id}", title_style))
#             elements.append(Spacer(1, 0.5*cm))
#             elements.append(Paragraph("Praco Packaging Supplies Ltd.", bold_style))
#             elements.append(Spacer(1, 0.3*cm))
#             elements.append(HRFlowable(width=doc.width, thickness=1, color=colors.black))
#             elements.append(Spacer(1, 0.5*cm))

#             shipping = self.shipping_address
#             billing = self.billing_address
#             shipping_address = billing_address = "N/A"
#             shipping_telephone = billing_telephone = "N/A"
#             if shipping:
#                 shipping_address = f"{shipping.first_name} {shipping.last_name}<br/>{shipping.street}<br/>{shipping.city}, {shipping.state} {shipping.postal_code}<br/>{shipping.country}"
#                 shipping_telephone = shipping.telephone_number or "N/A"
#             if billing:
#                 billing_address = f"{billing.first_name} {billing.last_name}<br/>{billing.street}<br/>{billing.city}, {billing.state} {billing.postal_code}<br/>{billing.country}"
#                 billing_telephone = billing.telephone_number or "N/A"
#             address_data = [
#                 [Paragraph("Bill To:", bold_style), Paragraph("Ship To:", bold_style)],
#                 [Paragraph(billing_address, normal_style), Paragraph(shipping_address, normal_style)],
#                 [Paragraph(f"Tel: {billing_telephone}", normal_style), Paragraph(f"Tel: {shipping_telephone}", normal_style)]
#             ]
#             address_table = Table(address_data, colWidths=[8*cm, 8*cm])
#             address_table.setStyle(TableStyle([
#                 ('VALIGN', (0, 0), (-1, -1), 'TOP'),
#                 ('LEFTPADDING', (0, 0), (-1, -1), 0),
#                 ('RIGHTPADDING', (0, 0), (-1, -1), 0),
#             ]))
#             elements.append(address_table)
#             elements.append(Spacer(1, 0.5*cm))

#             total_weight = self.calculate_total_weight()
#             due_date = self.created_at + timedelta(days=14)
#             total_due = self.calculate_total()
#             details_data = [
#                 [Paragraph("Date:", bold_style), Paragraph(self.created_at.strftime('%d/%m/%Y'), normal_style)],
#                 [Paragraph("Due Date:", bold_style), Paragraph(due_date.strftime('%d/%m/%Y'), normal_style)],
#                 [Paragraph("Total Weight:", bold_style), Paragraph(f"{total_weight:.3f} kg", normal_style)],
#                 [Paragraph("Total Due:", bold_style), Paragraph(f"€{total_due:.2f}", orange_style)]
#             ]
#             details_table = Table(details_data, colWidths=[4*cm, 12*cm])
#             details_table.setStyle(TableStyle([
#                 ('VALIGN', (0, 0), (-1, -1), 'TOP'),
#                 ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
#             ]))
#             elements.append(details_table)
#             elements.append(Spacer(1, 0.5*cm))

#             data = [['SKU', 'Packs', 'Units', 'Unit Price', 'Subtotal', 'Total']]
#             original_subtotal = Decimal('0.00')
#             items_exist = self.items.exists()
#             logger.info(f"Order {self.id} has items: {items_exist}")
#             if items_exist:
#                 for item in self.items.all():
#                     try:
#                         original_item_subtotal = item.calculate_original_subtotal()
#                         item_subtotal = item.calculate_subtotal()
#                         pricing_data = PricingTierData.objects.filter(pricing_tier=item.pricing_tier, item=item.item).first()
#                         unit_price = pricing_data.price if pricing_data else Decimal('0.00')
#                         discount_percent = item.calculate_discount_percentage()
#                         original_subtotal += item_subtotal
#                         total_display = f"€{item_subtotal:.2f}"
#                         if discount_percent > 0:
#                             total_display += f"\n{discount_percent}% off"
                        
#                         units_per_pack = item.item.units_per_pack or 1
#                         total_units = item.pack_quantity * units_per_pack
                        
#                         data.append([
#                             item.item.sku or "N/A",
#                             # item.item.title[:18] if item.item.title else "N/A",
#                             str(item.pack_quantity),
#                             str(total_units),
#                             f"€{unit_price:.2f}",
#                             f"€{original_item_subtotal:.2f}",
#                             total_display
#                         ])
#                     except Exception as e:
#                         logger.error(f"Error processing item {item.id} for invoice: {str(e)}")
#                         data.append(["N/A", "Error", "0", "0", "€0.00", "€0.00", "€0.00"])
#             else:
#                 logger.warning(f"No items found for order {self.id}")
#                 data.append(["N/A", "No items available", "0", "0", "€0.00", "€0.00", "€0.00"])
            
#             table = Table(data, colWidths=[3.5*cm, 3*cm, 2*cm, 2*cm, 2.5*cm, 2.5*cm, 2.5*cm])
#             table.setStyle(TableStyle([
#                 ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
#                 ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
#                 ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
#                 ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
#                 ('FONTSIZE', (0, 0), (-1, 0), 11),
#                 ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
#                 ('FONTSIZE', (0, 1), (-1, -1), 11),
#                 ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
#                 ('LEFTPADDING', (0, 0), (-1, -1), 5),
#                 ('RIGHTPADDING', (0, 0), (-1, -1), 5),
#             ]))
#             elements.append(table)
#             elements.append(Spacer(1, 0.5*cm))

#             subtotal = self.calculate_subtotal()
#             discount_amount = (subtotal * self.discount) / Decimal('100.00')
#             discounted_subtotal = subtotal - discount_amount
#             vat_amount = (discounted_subtotal * self.vat) / Decimal('100.00')
#             totals_data = [
#                 ['', 'Subtotal', f"€{subtotal:.2f}"],
#                 ['', f'Coupon Discount ({self.discount:.2f}%)', f"€{discount_amount:.2f}"],
#                 ['', f'VAT ({self.vat:.2f}%)', f"€{vat_amount:.2f}"],
#                 ['', 'Shipping Cost', f"€{self.shipping_cost:.2f}"],
#                 ['', 'Total', f"€{total_due:.2f}"]
#             ]
#             totals_table = Table(totals_data, colWidths=[9*cm, 3*cm, 3*cm])
#             totals_table.setStyle(TableStyle([
#                 ('ALIGN', (1, 0), (2, -1), 'RIGHT'),
#                 ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
#                 ('FONTSIZE', (0, 0), (-1, -1), 11),
#             ]))
#             elements.append(totals_table)
#             elements.append(Spacer(1, 0.5*cm))

#             notes = Paragraph(
#                 "Notes: 7-day exchange or refund policy for damaged goods. Contact us within 7 days for assistance. A 3% fee applies to cash payments.",
#                 small_style
#             )
#             elements.append(notes)
#             elements.append(Spacer(1, 0.5*cm))
#             elements.append(HRFlowable(width=doc.width, thickness=1, color=colors.black))
#             elements.append(Spacer(1, 0.5*cm))
#             footer = Paragraph(
#                 "Praco Packaging Supplies Ltd. | Account: 22035061 | Sort Code: 04-06-05 | VAT: 454687846",
#                 normal_style
#             )
#             elements.append(footer)

#             doc.build(elements)
#             buffer.seek(0)
#             logger.info(f"Successfully generated invoice PDF for order {self.id}")
#             return buffer
#         except Exception as e:
#             logger.error(f"Error generating invoice PDF for order {self.id}: {str(e)}")
#             return None

#     def generate_delivery_note_pdf(self):
#         try:
#             buffer = BytesIO()
#             doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
#             elements = []
#             styles = getSampleStyleSheet()
#             normal_style = styles['Normal']
#             normal_style.fontName = 'Helvetica'
#             normal_style.fontSize = 11
#             bold_style = ParagraphStyle(name='Bold', parent=normal_style, fontName='Helvetica-Bold')
#             title_style = ParagraphStyle(name='Title', fontName='Helvetica-Bold', fontSize=14, textColor=colors.black)
#             small_style = ParagraphStyle(name='Small', fontName='Helvetica', fontSize=8)

#             elements.append(Paragraph(f"Delivery Note #{self.id}", title_style))
#             elements.append(Spacer(1, 0.5*cm))
#             elements.append(Paragraph("Praco Packaging Supplies Ltd.", bold_style))
#             elements.append(Spacer(1, 0.3*cm))
#             elements.append(HRFlowable(width=doc.width, thickness=1, color=colors.black))
#             elements.append(Spacer(1, 0.5*cm))

#             shipping = self.shipping_address
#             shipping_address = "N/A"
#             shipping_telephone = "N/A"
#             if shipping:
#                 shipping_address = f"{shipping.first_name} {shipping.last_name}<br/>{shipping.street}<br/>{shipping.city}, {shipping.state} {shipping.postal_code}<br/>{shipping.country}"
#                 shipping_telephone = shipping.telephone_number or "N/A"
#             address_data = [
#                 [Paragraph("Ship To:", bold_style)],
#                 [Paragraph(shipping_address, normal_style)],
#                 [Paragraph(f"Tel: {shipping_telephone}", normal_style)]
#             ]
#             address_table = Table(address_data, colWidths=[16*cm])
#             address_table.setStyle(TableStyle([
#                 ('VALIGN', (0, 0), (-1, -1), 'TOP'),
#                 ('LEFTPADDING', (0, 0), (-1, -1), 0),
#                 ('RIGHTPADDING', (0, 0), (-1, -1), 0),
#             ]))
#             elements.append(address_table)
#             elements.append(Spacer(1, 0.5*cm))

#             total_weight = self.calculate_total_weight()
#             details_data = [
#                 [Paragraph("Date:", bold_style), Paragraph(self.created_at.strftime('%d/%m/%Y'), normal_style)],
#                 [Paragraph("Total Weight:", bold_style), Paragraph(f"{total_weight:.3f} kg", normal_style)],
#             ]
#             details_table = Table(details_data, colWidths=[4*cm, 12*cm])
#             details_table.setStyle(TableStyle([
#                 ('VALIGN', (0, 0), (-1, -1), 'TOP'),
#                 ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
#             ]))
#             elements.append(details_table)
#             elements.append(Spacer(1, 0.5*cm))

#             data = [['SKU', 'Packs', 'Units', 'Total Units']]
#             items_exist = self.items.exists()
#             logger.info(f"Order {self.id} has items for delivery note: {items_exist}")
#             if items_exist:
#                 for item in self.items.all():
#                     try:
#                         units_per_pack = item.item.units_per_pack or 1
#                         total_units = item.pack_quantity * units_per_pack
#                         data.append([
#                             item.item.sku or "N/A",
#                             # item.item.title[:18] if item.item.title else "N/A",
#                             str(item.pack_quantity),
#                             str(total_units),
#                             str(item.total_units)
#                         ])
#                     except Exception as e:
#                         logger.error(f"Error processing item {item.id} for delivery note: {str(e)}")
#                         data.append(["N/A", "Error", "0", "0", "0"])
#             else:
#                 logger.warning(f"No items found for order {self.id}")
#                 data.append(["N/A", "No items available", "0", "0", "0"])
            
#             table = Table(data, colWidths=[3.5*cm, 5*cm, 2*cm, 2*cm, 3*cm])
#             table.setStyle(TableStyle([
#                 ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
#                 ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
#                 ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
#                 ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
#                 ('FONTSIZE', (0, 0), (-1, 0), 11),
#                 ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
#                 ('FONTSIZE', (0, 1), (-1, -1), 11),
#                 ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
#                 ('LEFTPADDING', (0, 0), (-1, -1), 5),
#                 ('RIGHTPADDING', (0, 0), (-1, -1), 5),
#             ]))
#             elements.append(table)
#             elements.append(Spacer(1, 0.5*cm))

#             elements.append(HRFlowable(width=doc.width, thickness=1, color=colors.black))
#             elements.append(Spacer(1, 0.5*cm))
#             footer = Paragraph(
#                 "Praco Packaging Supplies Ltd. | Account: 22035061 | Sort Code: 04-06-05 | VAT: 454687846",
#                 normal_style
#             )
#             elements.append(footer)

#             doc.build(elements)
#             buffer.seek(0)
#             logger.info(f"Successfully generated delivery note PDF for order {self.id}")
#             return buffer
#         except Exception as e:
#             logger.error(f"Error generating delivery note PDF for order {self.id}: {str(e)}")
#             return None

#     def generate_paid_receipt_pdf(self):
#         try:
#             buffer = BytesIO()
#             doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
#             elements = []
#             styles = getSampleStyleSheet()
#             normal_style = styles['Normal']
#             normal_style.fontName = 'Helvetica'
#             normal_style.fontSize = 11
#             bold_style = ParagraphStyle(name='Bold', parent=normal_style, fontName='Helvetica-Bold')
#             title_style = ParagraphStyle(name='Title', fontName='Helvetica-Bold', fontSize=14, textColor=colors.black)
#             orange_style = ParagraphStyle(name='Orange', fontName='Helvetica-Bold', fontSize=12, textColor=HexColor('#F28C38'))
#             stamp_style = ParagraphStyle(name='Stamp', fontName='Helvetica-Bold', fontSize=24, textColor=colors.green)

#             elements.append(Paragraph("PAID", stamp_style))
#             elements.append(Spacer(1, 0.5*cm))

#             elements.append(Paragraph(f"Paid Receipt #{self.id}", title_style))
#             elements.append(Spacer(1, 0.5*cm))
#             elements.append(Paragraph("Praco Packaging Supplies Ltd.", bold_style))
#             elements.append(Spacer(1, 0.3*cm))
#             elements.append(HRFlowable(width=doc.width, thickness=1, color=colors.black))
#             elements.append(Spacer(1, 0.5*cm))

#             billing = self.billing_address
#             billing_address = "N/A"
#             billing_telephone = "N/A"
#             if billing:
#                 billing_address = f"{billing.first_name} {billing.last_name}<br/>{billing.street}<br/>{billing.city}, {billing.state} {billing.postal_code}<br/>{billing.country}"
#                 billing_telephone = billing.telephone_number or "N/A"
#             address_data = [
#                 [Paragraph("Bill To:", bold_style)],
#                 [Paragraph(billing_address, normal_style)],
#                 [Paragraph(f"Tel: {billing_telephone}", normal_style)]
#             ]
#             address_table = Table(address_data, colWidths=[16*cm])
#             address_table.setStyle(TableStyle([
#                 ('VALIGN', (0, 0), (-1, -1), 'TOP'),
#                 ('LEFTPADDING', (0, 0), (-1, -1), 0),
#                 ('RIGHTPADDING', (0, 0), (-1, -1), 0),
#             ]))
#             elements.append(address_table)
#             elements.append(Spacer(1, 0.5*cm))

#             payment_receipt_link = self.payment_receipt.url if self.payment_receipt else "N/A"
#             total_due = self.calculate_total()
#             details_data = [
#                 [Paragraph("Date:", bold_style), Paragraph(self.updated_at.strftime('%d/%m/%Y'), normal_style)],
#                 [Paragraph("Transaction ID:", bold_style), Paragraph(self.transaction_id or "N/A", normal_style)],
#                 [Paragraph("Payment Receipt:", bold_style), Paragraph(f'<a href="{payment_receipt_link}">View Receipt</a>', orange_style)],
#                 [Paragraph("Total Paid:", bold_style), Paragraph(f"€{total_due:.2f}", orange_style)]
#             ]
#             details_table = Table(details_data, colWidths=[4*cm, 12*cm])
#             details_table.setStyle(TableStyle([
#                 ('VALIGN', (0, 0), (-1, -1), 'TOP'),
#                 ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
#             ]))
#             elements.append(details_table)
#             elements.append(Spacer(1, 0.5*cm))

#             data = [['SKU', 'Packs', 'Units', 'Unit Price', 'Subtotal', 'Total']]
#             original_subtotal = Decimal('0.00')
#             items_exist = self.items.exists()
#             if items_exist:
#                 for item in self.items.all():
#                     try:
#                         original_item_subtotal = item.calculate_original_subtotal()
#                         item_subtotal = item.calculate_subtotal()
#                         pricing_data = PricingTierData.objects.filter(pricing_tier=item.pricing_tier, item=item.item).first()
#                         unit_price = pricing_data.price if pricing_data else Decimal('0.00')
#                         discount_percent = item.calculate_discount_percentage()
#                         original_subtotal += item_subtotal
#                         total_display = f"€{item_subtotal:.2f}"
#                         if discount_percent > 0:
#                             total_display += f"\n{discount_percent}% off"
                        
#                         units_per_pack = item.item.units_per_pack or 1
#                         total_units = item.pack_quantity * units_per_pack
                        
#                         data.append([
#                             item.item.sku or "N/A",
#                             # item.item.title[:18] if item.item.title else "N/A",
#                             str(item.pack_quantity),
#                             str(total_units),
#                             f"€{unit_price:.2f}",
#                             f"€{original_item_subtotal:.2f}",
#                             total_display
#                         ])
#                     except Exception as e:
#                         logger.error(f"Error processing item {item.id} for paid receipt: {str(e)}")
#                         data.append(["N/A", "Error", "0", "0", "€0.00", "€0.00", "€0.00"])
#             else:
#                 data.append(["N/A", "No items available", "0", "0", "€0.00", "€0.00", "€0.00"])
            
#             table = Table(data, colWidths=[3.5*cm, 3*cm, 2*cm, 2*cm, 2.5*cm, 2.5*cm, 2.5*cm])
#             table.setStyle(TableStyle([
#                 ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
#                 ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
#                 ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
#                 ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
#                 ('FONTSIZE', (0, 0), (-1, 0), 11),
#                 ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
#                 ('FONTSIZE', (0, 1), (-1, -1), 11),
#                 ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
#                 ('LEFTPADDING', (0, 0), (-1, -1), 5),
#                 ('RIGHTPADDING', (0, 0), (-1, -1), 5),
#             ]))
#             elements.append(table)
#             elements.append(Spacer(1, 0.5*cm))

#             subtotal = self.calculate_subtotal()
#             discount_amount = (subtotal * self.discount) / Decimal('100.00')
#             discounted_subtotal = subtotal - discount_amount
#             vat_amount = (discounted_subtotal * self.vat) / Decimal('100.00')
#             totals_data = [
#                 ['', 'Subtotal', f"€{subtotal:.2f}"],
#                 ['', f'Coupon Discount ({self.discount:.2f}%)', f"€{discount_amount:.2f}"],
#                 ['', f'VAT ({self.vat:.2f}%)', f"€{vat_amount:.2f}"],
#                 ['', 'Shipping Cost', f"€{self.shipping_cost:.2f}"],
#                 ['', 'Total', f"€{total_due:.2f}"]
#             ]
#             totals_table = Table(totals_data, colWidths=[9*cm, 3*cm, 3*cm])
#             totals_table.setStyle(TableStyle([
#                 ('ALIGN', (1, 0), (2, -1), 'RIGHT'),
#                 ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
#                 ('FONTSIZE', (0, 0), (-1, -1), 11),
#             ]))
#             elements.append(totals_table)
#             elements.append(Spacer(1, 0.5*cm))

#             elements.append(HRFlowable(width=doc.width, thickness=1, color=colors.black))
#             elements.append(Spacer(1, 0.5*cm))
#             footer = Paragraph(
#                 "Praco Packaging Supplies Ltd. | Account: 22035061 | Sort Code: 04-06-05 | VAT: 454687846",
#                 normal_style
#             )
#             elements.append(footer)

#             doc.build(elements)
#             buffer.seek(0)
#             logger.info(f"Successfully generated paid receipt PDF for order {self.id}")
#             return buffer
#         except Exception as e:
#             logger.error(f"Error generating paid receipt PDF for order {self.id}: {str(e)}")
#             return None

#     def generate_refund_receipt_pdf(self):
#         try:
#             buffer = BytesIO()
#             doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
#             elements = []
#             styles = getSampleStyleSheet()
#             normal_style = styles['Normal']
#             normal_style.fontName = 'Helvetica'
#             normal_style.fontSize = 11
#             bold_style = ParagraphStyle(name='Bold', parent=normal_style, fontName='Helvetica-Bold')
#             title_style = ParagraphStyle(name='Title', fontName='Helvetica-Bold', fontSize=14, textColor=colors.black)
#             orange_style = ParagraphStyle(name='Orange', fontName='Helvetica-Bold', fontSize=12, textColor=HexColor('#F28C38'))
#             stamp_style = ParagraphStyle(name='Stamp', fontName='Helvetica-Bold', fontSize=24, textColor=colors.red)

#             elements.append(Paragraph("REFUND", stamp_style))
#             elements.append(Spacer(1, 0.5*cm))

#             elements.append(Paragraph(f"Refund Receipt #{self.id}", title_style))
#             elements.append(Spacer(1, 0.5*cm))
#             elements.append(Paragraph("Praco Packaging Supplies Ltd.", bold_style))
#             elements.append(Spacer(1, 0.3*cm))
#             elements.append(HRFlowable(width=doc.width, thickness=1, color=colors.black))
#             elements.append(Spacer(1, 0.5*cm))

#             billing = self.billing_address
#             billing_address = "N/A"
#             billing_telephone = "N/A"
#             if billing:
#                 billing_address = f"{billing.first_name} {billing.last_name}<br/>{billing.street}<br/>{billing.city}, {billing.state} {billing.postal_code}<br/>{billing.country}"
#                 billing_telephone = billing.telephone_number or "N/A"
#             address_data = [
#                 [Paragraph("Bill To:", bold_style)],
#                 [Paragraph(billing_address, normal_style)],
#                 [Paragraph(f"Tel: {billing_telephone}", normal_style)]
#             ]
#             address_table = Table(address_data, colWidths=[16*cm])
#             address_table.setStyle(TableStyle([
#                 ('VALIGN', (0, 0), (-1, -1), 'TOP'),
#                 ('LEFTPADDING', (0, 0), (-1, -1), 0),
#                 ('RIGHTPADDING', (0, 0), (-1, -1), 0),
#             ]))
#             elements.append(address_table)
#             elements.append(Spacer(1, 0.5*cm))
#             refund_payment_receipt_link = self.refund_payment_receipt.url if self.refund_payment_receipt else "N/A"

#             total_due = self.calculate_total()
#             details_data = [
#                 [Paragraph("Date:", bold_style), Paragraph(self.updated_at.strftime('%d/%m/%Y'), normal_style)],
#                 [Paragraph("Refund Transaction ID:", bold_style), Paragraph(self.refund_transaction_id or "N/A", normal_style)],
#                 [Paragraph("Refund Payment Receipt:", bold_style), Paragraph(f'<a href="{refund_payment_receipt_link}">View Receipt</a>', orange_style)],
#                 [Paragraph("Total Refund:", bold_style), Paragraph(f"€{total_due:.2f}", orange_style)]
#             ]
#             details_table = Table(details_data, colWidths=[4*cm, 12*cm])
#             details_table.setStyle(TableStyle([
#                 ('VALIGN', (0, 0), (-1, -1), 'TOP'),
#                 ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
#             ]))
#             elements.append(details_table)
#             elements.append(Spacer(1, 0.5*cm))

#             data = [['SKU', 'Packs', 'Units', 'Unit Price', 'Subtotal', 'Total']]
#             original_subtotal = Decimal('0.00')
#             items_exist = self.items.exists()
#             if items_exist:
#                 for item in self.items.all():
#                     try:
#                         original_item_subtotal = item.calculate_original_subtotal()
#                         item_subtotal = item.calculate_subtotal()
#                         pricing_data = PricingTierData.objects.filter(pricing_tier=item.pricing_tier, item=item.item).first()
#                         unit_price = pricing_data.price if pricing_data else Decimal('0.00')
#                         discount_percent = item.calculate_discount_percentage()
#                         original_subtotal += item_subtotal
#                         total_display = f"€{item_subtotal:.2f}"
#                         if discount_percent > 0:
#                             total_display += f"\n{discount_percent}% off"
                        
#                         units_per_pack = item.item.units_per_pack or 1
#                         total_units = item.pack_quantity * units_per_pack
                        
#                         data.append([
#                             item.item.sku or "N/A",
#                             item.item.title[:18] if item.item.title else "N/A",
#                             str(item.pack_quantity),
#                             str(total_units),
#                             f"€{unit_price:.2f}",
#                             f"€{original_item_subtotal:.2f}",
#                             total_display
#                         ])
#                     except Exception as e:
#                         logger.error(f"Error processing item {item.id} for refund receipt: {str(e)}")
#                         data.append(["N/A", "Error", "0", "0", "€0.00", "€0.00", "€0.00"])
#             else:
#                 data.append(["N/A", "No items available", "0", "0", "€0.00", "€0.00", "€0.00"])
            
#             table = Table(data, colWidths=[3.5*cm, 3*cm, 2*cm, 2*cm, 2.5*cm, 2.5*cm, 2.5*cm])
#             table.setStyle(TableStyle([
#                 ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
#                 ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
#                 ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
#                 ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
#                 ('FONTSIZE', (0, 0), (-1, 0), 11),
#                 ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
#                 ('FONTSIZE', (0, 1), (-1, -1), 11),
#                 ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
#                 ('LEFTPADDING', (0, 0), (-1, -1), 5),
#                 ('RIGHTPADDING', (0, 0), (-1, -1), 5),
#             ]))
#             elements.append(table)
#             elements.append(Spacer(1, 0.5*cm))

#             subtotal = self.calculate_subtotal()
#             discount_amount = (subtotal * self.discount) / Decimal('100.00')
#             discounted_subtotal = subtotal - discount_amount
#             vat_amount = (discounted_subtotal * self.vat) / Decimal('100.00')
#             totals_data = [
#                 ['', 'Subtotal', f"€{subtotal:.2f}"],
#                 ['', f'Coupon Discount ({self.discount:.2f}%)', f"€{discount_amount:.2f}"],
#                 ['', f'VAT ({self.vat:.2f}%)', f"€{vat_amount:.2f}"],
#                 ['', 'Shipping Cost', f"€{self.shipping_cost:.2f}"],
#                 ['', 'Total', f"€{total_due:.2f}"]
#             ]
#             totals_table = Table(totals_data, colWidths=[9*cm, 3*cm, 3*cm])
#             totals_table.setStyle(TableStyle([
#                 ('ALIGN', (1, 0), (2, -1), 'RIGHT'),
#                 ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
#                 ('FONTSIZE', (0, 0), (-1, -1), 11),
#             ]))
#             elements.append(totals_table)
#             elements.append(Spacer(1, 0.5*cm))

#             elements.append(HRFlowable(width=doc.width, thickness=1, color=colors.black))
#             elements.append(Spacer(1, 0.5*cm))
#             footer = Paragraph(
#                 "Praco Packaging Supplies Ltd. | Account: 22035061 | Sort Code: 04-06-05 | VAT: 454687846",
#                 normal_style
#             )
#             elements.append(footer)

#             doc.build(elements)
#             buffer.seek(0)
#             logger.info(f"Successfully generated refund receipt PDF for order {self.id}")
#             return buffer
#         except Exception as e:
#             logger.error(f"Error generating refund receipt PDF for order {self.id}: {str(e)}")
#             return None

#     def generate_and_save_pdfs(self):
#         try:
#             items_exist = self.items.exists()
#             logger.info(f"Order {self.id} has items: {items_exist}")
#             if not items_exist:
#                 logger.warning(f"Skipping PDF generation for order {self.id} due to no items")
#                 return

#             self.update_order()

#             if not self.invoice:
#                 invoice_buffer = self.generate_invoice_pdf()
#                 if invoice_buffer:
#                     self.invoice.save(
#                         f'invoice_order_{self.id}.pdf',
#                         ContentFile(invoice_buffer.getvalue()),
#                         save=False
#                     )
#                     invoice_buffer.close()
#                     logger.info(f"Invoice PDF generated and saved for order {self.id} at {self.invoice.path}")
#                 else:
#                     logger.error(f"Invoice PDF generation failed for order {self.id}")

#             if not self.delivery_note:
#                 delivery_note_buffer = self.generate_delivery_note_pdf()
#                 if delivery_note_buffer:
#                     self.delivery_note.save(
#                         f'delivery_note_order_{self.id}.pdf',
#                         ContentFile(delivery_note_buffer.getvalue()),
#                         save=False
#                     )
#                     delivery_note_buffer.close()
#                     logger.info(f"Delivery note PDF generated and saved for order {self.id} at {self.delivery_note.path}")
#                 else:
#                     logger.error(f"Delivery note PDF generation failed for order {self.id}")

#             super(Order, self).save(update_fields=['invoice', 'delivery_note', 'discount'])
#             logger.info(f"Order {self.id} saved with updated invoice, delivery note, and discount fields")
#         except Exception as e:
#             logger.error(f"Error generating and saving PDFs for order {self.id}: {str(e)}")
#             raise

#     def generate_and_save_payment_receipts(self):
#         try:
#             update_fields = []
#             if self.payment_verified and self.payment_status == 'COMPLETED' and not self.paid_receipt:
#                 if not self.transaction_id:
#                     self.transaction_id = str(uuid.uuid4())
#                     update_fields.append('transaction_id')
#                 paid_receipt_buffer = self.generate_paid_receipt_pdf()
#                 if paid_receipt_buffer:
#                     self.paid_receipt.save(
#                         f'paid_receipt_order_{self.id}.pdf',
#                         ContentFile(paid_receipt_buffer.getvalue()),
#                         save=False
#                     )
#                     paid_receipt_buffer.close()
#                     update_fields.append('paid_receipt')
#                     logger.info(f"Paid receipt PDF generated and saved for order {self.id} at {self.paid_receipt.path}")
#                 else:
#                     logger.error(f"Paid receipt PDF generation failed for order {self.id}")

#             if self.payment_status == 'REFUND' and self.transaction_id and self.payment_receipt and self.refund_transaction_id and self.refund_payment_receipt and self.paid_receipt and not self.refund_receipt:
#                 refund_receipt_buffer = self.generate_refund_receipt_pdf()
#                 if refund_receipt_buffer:
#                     self.refund_receipt.save(
#                         f'refund_receipt_order_{self.id}.pdf',
#                         ContentFile(refund_receipt_buffer.getvalue()),
#                         save=False
#                     )
#                     refund_receipt_buffer.close()
#                     update_fields.append('refund_receipt')
#                     logger.info(f"Refund receipt PDF generated and saved for order {self.id} at {self.refund_receipt.path}")
#                 else:
#                     logger.error(f"Refund receipt PDF generation failed for order {self.id}")

#             if update_fields:
#                 super(Order, self).save(update_fields=update_fields)
#                 logger.info(f"Order {self.id} saved with updated receipt fields: {update_fields}")
#         except Exception as e:
#             logger.error(f"Error generating and saving payment receipts for order {self.id}: {str(e)}")
#             raise

#     def save(self, *args, **kwargs):
#         self.full_clean()
#         super().save(*args, **kwargs)
#         update_fields = kwargs.get('update_fields', [])
#         if self.items.exists() and not any(field in update_fields for field in ['invoice', 'delivery_note', 'discount', 'paid_receipt', 'refund_receipt']):
#             self.update_order()
#             self.generate_and_save_pdfs()
#             if self.payment_verified or self.payment_status in ['COMPLETED', 'REFUND']:
#                 self.generate_and_save_payment_receipts()

#     def update_order_items(self, new_item):
#         """Update order with a new or existing item."""
#         try:
#             OrderItem.objects.create(
#                 order=self,
#                 item=new_item['item'],
#                 pricing_tier=new_item.get('pricing_tier'),
#                 pack_quantity=new_item.get('pack_quantity', 1),
#                 unit_type=new_item.get('unit_type', 'pack'),
#                 user_exclusive_price=new_item.get('user_exclusive_price')
#             )
#             self.update_order()
#             for field in ['invoice', 'delivery_note', 'paid_receipt', 'refund_receipt']:
#                 file_field = getattr(self, field)
#                 if file_field:
#                     file_field.delete(save=False)
#             self.generate_and_save_pdfs()
#             if self.payment_verified or self.payment_status in ['COMPLETED', 'REFUND']:
#                 self.generate_and_save_payment_receipts()
#             logger.info(f"Updated order {self.id} with new item")
#         except Exception as e:
#             logger.error(f"Error updating order {self.id}: {str(e)}")
#             raise

#     def delete(self, *args, **kwargs):
#         try:
#             for field in ['payment_receipt', 'refund_payment_receipt', 'paid_receipt', 'refund_receipt', 'invoice', 'delivery_note']:
#                 file_field = getattr(self, field)
#                 if file_field:
#                     file_field.delete(save=False)
#                     logger.info(f"Deleted {field} for order {self.id}")
#         except Exception as e:
#             logger.error(f"Error deleting files for order {self.id}: {str(e)}")
#         super().delete(*args, **kwargs)

#     def __str__(self):
#         return f"Order {self.id} - {self.status}"

# class Order(models.Model):
#     STATUS_CHOICES = (
#         ('PENDING', 'Pending'),
#         ('PROCESSING', 'Processing'),
#         ('SHIPPED', 'Shipped'),
#         ('DELIVERED', 'Delivered'),
#         ('CANCELLED', 'Cancelled'),
#         ('RETURNED', 'Returned'),
#     )
#     PAYMENT_STATUS_CHOICES = (
#         ('PENDING', 'Pending'),
#         ('COMPLETED', 'Completed'),
#         ('FAILED', 'Failed'),
#         ('REFUND', 'Refund'),
#     )
#     PAYMENT_METHOD_CHOICES = (
#         ('manual_payment', 'Manual Payment'),
#         ('stripe', 'Stripe Payment'),
#     )

#     user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
#     shipping_address = models.ForeignKey('ShippingAddress', on_delete=models.SET_NULL, null=True)
#     billing_address = models.ForeignKey('BillingAddress', on_delete=models.SET_NULL, null=True)
#     shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, editable=False)
#     vat = models.DecimalField(
#         max_digits=5,
#         decimal_places=2,
#         default=Decimal('20.00'),
#         help_text="VAT percentage (e.g., 20 for 20%)."
#     )
#     discount = models.DecimalField(
#         max_digits=5,
#         decimal_places=2,
#         default=Decimal('0.00'),
#         help_text="Discount percentage (e.g., 10 for 10%)."
#     )
#     status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
#     payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='PENDING')
#     payment_verified = models.BooleanField(default=False)
#     payment_method = models.CharField(
#         max_length=50,
#         choices=PAYMENT_METHOD_CHOICES,
#         default='manual_payment'
#     )
#     transaction_id = models.CharField(max_length=100, blank=True, null=True)
#     payment_receipt = models.FileField(upload_to='receipts/', blank=True, null=True)
#     refund_transaction_id = models.CharField(max_length=100, blank=True, null=True)
#     refund_payment_receipt = models.FileField(upload_to='refund_receipts/', blank=True, null=True)
#     paid_receipt = models.FileField(upload_to='paid_receipts/', blank=True, null=True, editable=False)
#     refund_receipt = models.FileField(upload_to='refund_receipts/', blank=True, null=True, editable=False)
#     invoice = models.FileField(upload_to='invoices/', null=True, blank=True, editable=False)
#     delivery_note = models.FileField(upload_to='delivery_notes/', null=True, blank=True, editable=False)
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)

#     class Meta:
#         indexes = [
#             models.Index(fields=['user']),
#             models.Index(fields=['created_at']),
#         ]
#         verbose_name = 'order'
#         verbose_name_plural = 'orders'

#     def clean(self):
#         errors = {}
#         if self.payment_verified:
#             if not self.transaction_id:
#                 errors['transaction_id'] = 'Transaction ID is required when payment is verified.'
#             if not self.payment_receipt:
#                 errors['payment_receipt'] = 'Payment receipt is required when payment is verified.'
#             if self.payment_status in ['FAILED', 'PENDING']:
#                 errors['payment_status'] = 'Payment status must be Completed/Refunded when payment is verified.'
        
#         if self.payment_status == 'COMPLETED':
#             if not self.transaction_id:
#                 errors['transaction_id'] = 'Transaction ID is required when payment status is Completed.'
#             if not self.payment_receipt:
#                 errors['payment_receipt'] = 'Payment receipt is required when payment status is Completed.'
        
#         elif self.payment_status == 'REFUND':
#             if not self.transaction_id:
#                 errors['transaction_id'] = 'Transaction ID is required when payment status is Refunded.'
#             if not self.payment_receipt:
#                 errors['payment_receipt'] = 'Payment receipt is required when payment status is Refunded.'
#             if not self.refund_transaction_id:
#                 errors['refund_transaction_id'] = 'Refunded transaction ID is required when payment status is Refunded.'
#             if not self.refund_payment_receipt:
#                 errors['refund_payment_receipt'] = 'Refunded payment receipt is required when payment status is Refunded.'

#         for field, field_name in [(self.payment_receipt, 'payment_receipt'), (self.refund_payment_receipt, 'refund_payment_receipt')]:
#             if field:
#                 ext = field.name.lower().split('.')[-1]
#                 if ext not in ['png', 'jpg', 'jpeg', 'pdf']:
#                     errors[field_name] = 'File must be a PNG, JPG, or PDF.'

#         if errors:
#             raise ValidationError(errors)

#         if self.payment_status == 'REFUND' and not self.paid_receipt:
#             raise ValidationError({'__all__': 'Paid receipt must exist when payment status is Refunded.'})

#     def calculate_subtotal(self):
#         try:
#             total = Decimal('0.00')
#             for item in self.items.all():
#                 item_subtotal = item.calculate_subtotal()
#                 total += item_subtotal
#             logger.info(f"Order {self.id} subtotal: {total}")
#             return total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
#         except Exception as e:
#             logger.error(f"Error calculating subtotal for order {self.id}: {str(e)}")
#             return Decimal('0.00')

#     def calculate_original_subtotal(self):
#         try:
#             total = self.calculate_subtotal()
#             logger.info(f"Order {self.id} original subtotal: {total}")
#             return total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
#         except Exception as e:
#             logger.error(f"Error calculating original subtotal for order {self.id}: {str(e)}")
#             return Decimal('0.00')

#     def calculate_total(self):
#         try:
#             subtotal = self.calculate_subtotal()
#             discount_amount = (subtotal * self.discount) / Decimal('100.00')
#             discounted_subtotal = subtotal - discount_amount
#             vat_amount = (discounted_subtotal * self.vat) / Decimal('100.00')
#             shipping_cost = Decimal(str(self.shipping_cost)).quantize(Decimal('0.01'))
#             total = (discounted_subtotal + vat_amount + shipping_cost).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
#             logger.info(f"Order {self.id} total: {total} (subtotal={subtotal}, discount={self.discount}%, vat={self.vat}%, shipping={shipping_cost})")
#             return total
#         except Exception as e:
#             logger.error(f"Error calculating total for order {self.id}: {str(e)}")
#             return Decimal('0.00')

#     def calculate_total_weight(self):
#         try:
#             total_weight = Decimal('0.00000000')
#             for item in self.items.all():
#                 item_weight_kg = item.calculate_weight()
#                 total_units = item.total_units
#                 total_weight += item_weight_kg * Decimal(total_units)
#             logger.info(f"Order {self.id} total weight: {total_weight}")
#             return total_weight.quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)
#         except Exception as e:
#             logger.error(f"Error calculating total weight for order {self.id}: {str(e)}")
#             return Decimal('0.00000000')

#     def calculate_total_units_and_packs(self):
#         try:
#             total_units = 0
#             total_packs = 0
#             for item in self.items.all():
#                 units_per_pack = item.item.units_per_pack or 1
#                 total_units += item.pack_quantity * units_per_pack
#                 total_packs += item.pack_quantity
#             logger.info(f"Order {self.id} total units: {total_units}, total packs: {total_packs}")
#             return total_units, total_packs
#         except Exception as e:
#             logger.error(f"Error calculating units and packs for order {self.id}: {str(e)}")
#             return 0, 0

#     def update_order(self):
#         try:
#             self.calculate_total()
#             super().save(update_fields=['discount'])
#             logger.info(f"Updated order {self.id} calculations")
#         except Exception as e:
#             logger.error(f"Error updating order {self.id}: {str(e)}")

#     def generate_invoice_pdf(self):
#         try:
#             buffer = BytesIO()
#             doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
#             elements = []
#             styles = getSampleStyleSheet()
#             normal_style = styles['Normal']
#             normal_style.fontName = 'Helvetica'
#             normal_style.fontSize = 11
#             bold_style = ParagraphStyle(name='Bold', parent=normal_style, fontName='Helvetica-Bold')
#             title_style = ParagraphStyle(name='Title', fontName='Helvetica-Bold', fontSize=14, textColor=colors.black)
#             orange_style = ParagraphStyle(name='Orange', fontName='Helvetica-Bold', fontSize=12, textColor=HexColor('#F28C38'))
#             small_style = ParagraphStyle(name='Small', fontName='Helvetica', fontSize=8)

#             elements.append(Paragraph(f"Invoice #{self.id}", title_style))
#             elements.append(Spacer(1, 0.5*cm))
#             elements.append(Paragraph("Praco Packaging Supplies Ltd.", bold_style))
#             elements.append(Spacer(1, 0.3*cm))
#             elements.append(HRFlowable(width=doc.width, thickness=1, color=colors.black))
#             elements.append(Spacer(1, 0.5*cm))

#             shipping = self.shipping_address
#             billing = self.billing_address
#             shipping_address = billing_address = "N/A"
#             shipping_telephone = billing_telephone = "N/A"
#             if shipping:
#                 shipping_address = f"{shipping.first_name} {shipping.last_name}<br/>{shipping.street}<br/>{shipping.city}, {shipping.state} {shipping.postal_code}<br/>{shipping.country}"
#                 shipping_telephone = shipping.telephone_number or "N/A"
#             if billing:
#                 billing_address = f"{billing.first_name} {billing.last_name}<br/>{billing.street}<br/>{billing.city}, {billing.state} {billing.postal_code}<br/>{billing.country}"
#                 billing_telephone = billing.telephone_number or "N/A"
#             address_data = [
#                 [Paragraph("Bill To:", bold_style), Paragraph("Ship To:", bold_style)],
#                 [Paragraph(billing_address, normal_style), Paragraph(shipping_address, normal_style)],
#                 [Paragraph(f"Tel: {billing_telephone}", normal_style), Paragraph(f"Tel: {shipping_telephone}", normal_style)]
#             ]
#             address_table = Table(address_data, colWidths=[8*cm, 8*cm])
#             address_table.setStyle(TableStyle([
#                 ('VALIGN', (0, 0), (-1, -1), 'TOP'),
#                 ('LEFTPADDING', (0, 0), (-1, -1), 0),
#                 ('RIGHTPADDING', (0, 0), (-1, -1), 0),
#             ]))
#             elements.append(address_table)
#             elements.append(Spacer(1, 0.5*cm))

#             total_weight = self.calculate_total_weight()
#             due_date = self.created_at + timedelta(days=14)
#             total_due = self.calculate_total()
#             details_data = [
#                 [Paragraph("Date:", bold_style), Paragraph(self.created_at.strftime('%d/%m/%Y'), normal_style)],
#                 [Paragraph("Due Date:", bold_style), Paragraph(due_date.strftime('%d/%m/%Y'), normal_style)],
#                 [Paragraph("Total Weight:", bold_style), Paragraph(f"{total_weight:.3f} kg", normal_style)],
#                 [Paragraph("Total Due:", bold_style), Paragraph(f"£{total_due:.2f}", orange_style)]
#             ]
#             if self.payment_method == 'stripe':
#                 transaction = self.transactions.first()
#                 details_data.append([Paragraph("Payment Method:", bold_style), Paragraph("Stripe", normal_style)])
#                 if transaction:
#                     details_data.append([Paragraph("Transaction ID:", bold_style), Paragraph(transaction.stripe_payment_intent_id, normal_style)])
#             details_table = Table(details_data, colWidths=[4*cm, 12*cm])
#             details_table.setStyle(TableStyle([
#                 ('VALIGN', (0, 0), (-1, -1), 'TOP'),
#                 ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
#             ]))
#             elements.append(details_table)
#             elements.append(Spacer(1, 0.5*cm))

#             data = [['SKU', 'Packs', 'Units', 'Unit Price', 'Subtotal', 'Total']]
#             original_subtotal = Decimal('0.00')
#             items_exist = self.items.exists()
#             logger.info(f"Order {self.id} has items: {items_exist}")
#             if items_exist:
#                 for item in self.items.all():
#                     try:
#                         original_item_subtotal = item.calculate_original_subtotal()
#                         item_subtotal = item.calculate_subtotal()
#                         pricing_data = PricingTierData.objects.filter(pricing_tier=item.pricing_tier, item=item.item).first()
#                         unit_price = pricing_data.price if pricing_data else Decimal('0.00')
#                         discount_percent = item.calculate_discount_percentage()
#                         original_subtotal += item_subtotal
#                         total_display = f"£{item_subtotal:.2f}"
#                         if discount_percent > 0:
#                             total_display += f"\n{discount_percent}% off"
                        
#                         units_per_pack = item.item.units_per_pack or 1
#                         total_units = item.pack_quantity * units_per_pack
                        
#                         data.append([
#                             item.item.sku or "N/A",
#                             str(item.pack_quantity),
#                             str(total_units),
#                             f"£{unit_price:.2f}",
#                             f"£{original_item_subtotal:.2f}",
#                             total_display
#                         ])
#                     except Exception as e:
#                         logger.error(f"Error processing item {item.id} for invoice: {str(e)}")
#                         data.append(["N/A", "Error", "0", "0", "£0.00", "£0.00"])
#             else:
#                 logger.warning(f"No items found for order {self.id}")
#                 data.append(["N/A", "No items available", "0", "0", "£0.00", "£0.00"])
            
#             table = Table(data, colWidths=[3.5*cm, 3*cm, 2*cm, 2*cm, 2.5*cm, 2.5*cm])
#             table.setStyle(TableStyle([
#                 ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
#                 ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
#                 ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
#                 ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
#                 ('FONTSIZE', (0, 0), (-1, 0), 11),
#                 ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
#                 ('FONTSIZE', (0, 1), (-1, -1), 11),
#                 ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
#                 ('LEFTPADDING', (0, 0), (-1, -1), 5),
#                 ('RIGHTPADDING', (0, 0), (-1, -1), 5),
#             ]))
#             elements.append(table)
#             elements.append(Spacer(1, 0.5*cm))

#             subtotal = self.calculate_subtotal()
#             discount_amount = (subtotal * self.discount) / Decimal('100.00')
#             discounted_subtotal = subtotal - discount_amount
#             vat_amount = (discounted_subtotal * self.vat) / Decimal('100.00')
#             totals_data = [
#                 ['', 'Subtotal', f"£{subtotal:.2f}"],
#                 ['', f'Coupon Discount ({self.discount:.2f}%)', f"£{discount_amount:.2f}"],
#                 ['', f'VAT ({self.vat:.2f}%)', f"£{vat_amount:.2f}"],
#                 ['', 'Shipping Cost', f"£{self.shipping_cost:.2f}"],
#                 ['', 'Total', f"£{total_due:.2f}"]
#             ]
#             totals_table = Table(totals_data, colWidths=[9*cm, 3*cm, 3*cm])
#             totals_table.setStyle(TableStyle([
#                 ('ALIGN', (1, 0), (2, -1), 'RIGHT'),
#                 ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
#                 ('FONTSIZE', (0, 0), (-1, -1), 11),
#             ]))
#             elements.append(totals_table)
#             elements.append(Spacer(1, 0.5*cm))

#             notes = Paragraph(
#                 "Notes: 7-day exchange or refund policy for damaged goods. Contact us within 7 days for assistance. A 3% fee applies to cash payments.",
#                 small_style
#             )
#             elements.append(notes)
#             elements.append(Spacer(1, 0.5*cm))
#             elements.append(HRFlowable(width=doc.width, thickness=1, color=colors.black))
#             elements.append(Spacer(1, 0.5*cm))
#             footer = Paragraph(
#                 "Praco Packaging Supplies Ltd. | Account: 22035061 | Sort Code: 04-06-05 | VAT: 454687846",
#                 normal_style
#             )
#             elements.append(footer)

#             doc.build(elements)
#             buffer.seek(0)
#             logger.info(f"Successfully generated invoice PDF for order {self.id}")
#             return buffer
#         except Exception as e:
#             logger.error(f"Error generating invoice PDF for order {self.id}: {str(e)}")
#             return None

#     def generate_delivery_note_pdf(self):
#         try:
#             buffer = BytesIO()
#             doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
#             elements = []
#             styles = getSampleStyleSheet()
#             normal_style = styles['Normal']
#             normal_style.fontName = 'Helvetica'
#             normal_style.fontSize = 11
#             bold_style = ParagraphStyle(name='Bold', parent=normal_style, fontName='Helvetica-Bold')
#             title_style = ParagraphStyle(name='Title', fontName='Helvetica-Bold', fontSize=14, textColor=colors.black)
#             small_style = ParagraphStyle(name='Small', fontName='Helvetica', fontSize=8)

#             elements.append(Paragraph(f"Delivery Note #{self.id}", title_style))
#             elements.append(Spacer(1, 0.5*cm))
#             elements.append(Paragraph("Praco Packaging Supplies Ltd.", bold_style))
#             elements.append(Spacer(1, 0.3*cm))
#             elements.append(HRFlowable(width=doc.width, thickness=1, color=colors.black))
#             elements.append(Spacer(1, 0.5*cm))

#             shipping = self.shipping_address
#             shipping_address = "N/A"
#             shipping_telephone = "N/A"
#             if shipping:
#                 shipping_address = f"{shipping.first_name} {shipping.last_name}<br/>{shipping.street}<br/>{shipping.city}, {shipping.state} {shipping.postal_code}<br/>{shipping.country}"
#                 shipping_telephone = shipping.telephone_number or "N/A"
#             address_data = [
#                 [Paragraph("Ship To:", bold_style)],
#                 [Paragraph(shipping_address, normal_style)],
#                 [Paragraph(f"Tel: {shipping_telephone}", normal_style)]
#             ]
#             address_table = Table(address_data, colWidths=[16*cm])
#             address_table.setStyle(TableStyle([
#                 ('VALIGN', (0, 0), (-1, -1), 'TOP'),
#                 ('LEFTPADDING', (0, 0), (-1, -1), 0),
#                 ('RIGHTPADDING', (0, 0), (-1, -1), 0),
#             ]))
#             elements.append(address_table)
#             elements.append(Spacer(1, 0.5*cm))

#             total_weight = self.calculate_total_weight()
#             details_data = [
#                 [Paragraph("Date:", bold_style), Paragraph(self.created_at.strftime('%d/%m/%Y'), normal_style)],
#                 [Paragraph("Total Weight:", bold_style), Paragraph(f"{total_weight:.3f} kg", normal_style)],
#             ]
#             if self.payment_method == 'stripe':
#                 transaction = self.transactions.first()
#                 if transaction:
#                     details_data.append([Paragraph("Transaction ID:", bold_style), Paragraph(transaction.stripe_payment_intent_id, normal_style)])
#             details_table = Table(details_data, colWidths=[4*cm, 12*cm])
#             details_table.setStyle(TableStyle([
#                 ('VALIGN', (0, 0), (-1, -1), 'TOP'),
#                 ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
#             ]))
#             elements.append(details_table)
#             elements.append(Spacer(1, 0.5*cm))

#             data = [['SKU', 'Packs', 'Units', 'Total Units']]
#             items_exist = self.items.exists()
#             logger.info(f"Order {self.id} has items for delivery note: {items_exist}")
#             if items_exist:
#                 for item in self.items.all():
#                     try:
#                         units_per_pack = item.item.units_per_pack or 1
#                         total_units = item.pack_quantity * units_per_pack
#                         data.append([
#                             item.item.sku or "N/A",
#                             str(item.pack_quantity),
#                             str(total_units),
#                             str(item.total_units)
#                         ])
#                     except Exception as e:
#                         logger.error(f"Error processing item {item.id} for delivery note: {str(e)}")
#                         data.append(["N/A", "Error", "0", "0"])
#             else:
#                 logger.warning(f"No items found for order {self.id}")
#                 data.append(["N/A", "No items available", "0", "0"])
            
#             table = Table(data, colWidths=[3.5*cm, 5*cm, 2*cm, 2*cm])
#             table.setStyle(TableStyle([
#                 ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
#                 ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
#                 ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
#                 ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
#                 ('FONTSIZE', (0, 0), (-1, 0), 11),
#                 ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
#                 ('FONTSIZE', (0, 1), (-1, -1), 11),
#                 ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
#                 ('LEFTPADDING', (0, 0), (-1, -1), 5),
#                 ('RIGHTPADDING', (0, 0), (-1, -1), 5),
#             ]))
#             elements.append(table)
#             elements.append(Spacer(1, 0.5*cm))

#             elements.append(HRFlowable(width=doc.width, thickness=1, color=colors.black))
#             elements.append(Spacer(1, 0.5*cm))
#             footer = Paragraph(
#                 "Praco Packaging Supplies Ltd. | Account: 22035061 | Sort Code: 04-06-05 | VAT: 454687846",
#                 normal_style
#             )
#             elements.append(footer)

#             doc.build(elements)
#             buffer.seek(0)
#             logger.info(f"Successfully generated delivery note PDF for order {self.id}")
#             return buffer
#         except Exception as e:
#             logger.error(f"Error generating delivery note PDF for order {self.id}: {str(e)}")
#             return None

#     def generate_paid_receipt_pdf(self):
#         try:
#             buffer = BytesIO()
#             doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
#             elements = []
#             styles = getSampleStyleSheet()
#             normal_style = styles['Normal']
#             normal_style.fontName = 'Helvetica'
#             normal_style.fontSize = 11
#             bold_style = ParagraphStyle(name='Bold', parent=normal_style, fontName='Helvetica-Bold')
#             title_style = ParagraphStyle(name='Title', fontName='Helvetica-Bold', fontSize=14, textColor=colors.black)
#             orange_style = ParagraphStyle(name='Orange', fontName='Helvetica-Bold', fontSize=12, textColor=HexColor('#F28C38'))
#             stamp_style = ParagraphStyle(name='Stamp', fontName='Helvetica-Bold', fontSize=24, textColor=colors.green)

#             elements.append(Paragraph("PAID", stamp_style))
#             elements.append(Spacer(1, 0.5*cm))

#             elements.append(Paragraph(f"Paid Receipt #{self.id}", title_style))
#             elements.append(Spacer(1, 0.5*cm))
#             elements.append(Paragraph("Praco Packaging Supplies Ltd.", bold_style))
#             elements.append(Spacer(1, 0.3*cm))
#             elements.append(HRFlowable(width=doc.width, thickness=1, color=colors.black))
#             elements.append(Spacer(1, 0.5*cm))

#             billing = self.billing_address
#             billing_address = "N/A"
#             billing_telephone = "N/A"
#             if billing:
#                 billing_address = f"{billing.first_name} {billing.last_name}<br/>{billing.street}<br/>{billing.city}, {billing.state} {billing.postal_code}<br/>{billing.country}"
#                 billing_telephone = billing.telephone_number or "N/A"
#             address_data = [
#                 [Paragraph("Bill To:", bold_style)],
#                 [Paragraph(billing_address, normal_style)],
#                 [Paragraph(f"Tel: {billing_telephone}", normal_style)]
#             ]
#             address_table = Table(address_data, colWidths=[16*cm])
#             address_table.setStyle(TableStyle([
#                 ('VALIGN', (0, 0), (-1, -1), 'TOP'),
#                 ('LEFTPADDING', (0, 0), (-1, -1), 0),
#                 ('RIGHTPADDING', (0, 0), (-1, -1), 0),
#             ]))
#             elements.append(address_table)
#             elements.append(Spacer(1, 0.5*cm))

#             payment_receipt_link = self.payment_receipt.url if self.payment_receipt else "N/A"
#             total_due = self.calculate_total()
#             details_data = [
#                 [Paragraph("Date:", bold_style), Paragraph(self.updated_at.strftime('%d/%m/%Y'), normal_style)],
#                 [Paragraph("Transaction ID:", bold_style), Paragraph(self.transaction_id or "N/A", normal_style)],
#                 [Paragraph("Payment Receipt:", bold_style), Paragraph(f'<a href="{payment_receipt_link}">View Receipt</a>', orange_style)],
#                 [Paragraph("Total Paid:", bold_style), Paragraph(f"£{total_due:.2f}", orange_style)],
#             ]
#             if self.payment_method == 'stripe':
#                 transaction = self.transactions.first()
#                 if transaction:
#                     details_data.insert(1, [Paragraph("Payment Method:", bold_style), Paragraph("Stripe", normal_style)])
#             details_table = Table(details_data, colWidths=[4*cm, 12*cm])
#             details_table.setStyle(TableStyle([
#                 ('VALIGN', (0, 0), (-1, -1), 'TOP'),
#                 ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
#             ]))
#             elements.append(details_table)
#             elements.append(Spacer(1, 0.5*cm))

#             data = [['SKU', 'Packs', 'Units', 'Unit Price', 'Subtotal', 'Total']]
#             original_subtotal = Decimal('0.00')
#             items_exist = self.items.exists()
#             if items_exist:
#                 for item in self.items.all():
#                     try:
#                         original_item_subtotal = item.calculate_original_subtotal()
#                         item_subtotal = item.calculate_subtotal()
#                         pricing_data = PricingTierData.objects.filter(pricing_tier=item.pricing_tier, item=item.item).first()
#                         unit_price = pricing_data.price if pricing_data else Decimal('0.00')
#                         discount_percent = item.calculate_discount_percentage()
#                         original_subtotal += item_subtotal
#                         total_display = f"£{item_subtotal:.2f}"
#                         if discount_percent > 0:
#                             total_display += f"\n{discount_percent}% off"
                        
#                         units_per_pack = item.item.units_per_pack or 1
#                         total_units = item.pack_quantity * units_per_pack
                        
#                         data.append([
#                             item.item.sku or "N/A",
#                             str(item.pack_quantity),
#                             str(total_units),
#                             f"£{unit_price:.2f}",
#                             f"£{original_item_subtotal:.2f}",
#                             total_display
#                         ])
#                     except Exception as e:
#                         logger.error(f"Error processing item {item.id} for paid receipt: {str(e)}")
#                         data.append(["N/A", "Error", "0", "0", "£0.00", "£0.00"])
#             else:
#                 data.append(["N/A", "No items available", "0", "0", "£0.00", "£0.00"])
            
#             table = Table(data, colWidths=[3.5*cm, 3*cm, 2*cm, 2*cm, 2.5*cm, 2.5*cm])
#             table.setStyle(TableStyle([
#                 ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
#                 ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
#                 ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
#                 ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
#                 ('FONTSIZE', (0, 0), (-1, 0), 11),
#                 ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
#                 ('FONTSIZE', (0, 1), (-1, -1), 11),
#                 ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
#                 ('LEFTPADDING', (0, 0), (-1, -1), 5),
#                 ('RIGHTPADDING', (0, 0), (-1, -1), 5),
#             ]))
#             elements.append(table)
#             elements.append(Spacer(1, 0.5*cm))

#             subtotal = self.calculate_subtotal()
#             discount_amount = (subtotal * self.discount) / Decimal('100.00')
#             discounted_subtotal = subtotal - discount_amount
#             vat_amount = (discounted_subtotal * self.vat) / Decimal('100.00')
#             totals_data = [
#                 ['', 'Subtotal', f"£{subtotal:.2f}"],
#                 ['', f'Coupon Discount ({self.discount:.2f}%)', f"£{discount_amount:.2f}"],
#                 ['', f'VAT ({self.vat:.2f}%)', f"£{vat_amount:.2f}"],
#                 ['', 'Shipping Cost', f"£{self.shipping_cost:.2f}"],
#                 ['', 'Total', f"£{total_due:.2f}"]
#             ]
#             totals_table = Table(totals_data, colWidths=[9*cm, 3*cm, 3*cm])
#             totals_table.setStyle(TableStyle([
#                 ('ALIGN', (1, 0), (2, -1), 'RIGHT'),
#                 ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
#                 ('FONTSIZE', (0, 0), (-1, -1), 11),
#             ]))
#             elements.append(totals_table)
#             elements.append(Spacer(1, 0.5*cm))

#             elements.append(HRFlowable(width=doc.width, thickness=1, color=colors.black))
#             elements.append(Spacer(1, 0.5*cm))
#             footer = Paragraph(
#                 "Praco Packaging Supplies Ltd. | Account: 22035061 | Sort Code: 04-06-05 | VAT: 454687846",
#                 normal_style
#             )
#             elements.append(footer)

#             doc.build(elements)
#             buffer.seek(0)
#             logger.info(f"Successfully generated paid receipt PDF for order {self.id}")
#             return buffer
#         except Exception as e:
#             logger.error(f"Error generating paid receipt PDF for order {self.id}: {str(e)}")
#             return None

#     def generate_refund_receipt_pdf(self):
#         try:
#             buffer = BytesIO()
#             doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
#             elements = []
#             styles = getSampleStyleSheet()
#             normal_style = styles['Normal']
#             normal_style.fontName = 'Helvetica'
#             normal_style.fontSize = 11
#             bold_style = ParagraphStyle(name='Bold', parent=normal_style, fontName='Helvetica-Bold')
#             title_style = ParagraphStyle(name='Title', fontName='Helvetica-Bold', fontSize=14, textColor=colors.black)
#             orange_style = ParagraphStyle(name='Orange', fontName='Helvetica-Bold', fontSize=12, textColor=HexColor('#F28C38'))
#             stamp_style = ParagraphStyle(name='Stamp', fontName='Helvetica-Bold', fontSize=24, textColor=colors.red)

#             elements.append(Paragraph("REFUND", stamp_style))
#             elements.append(Spacer(1, 0.5*cm))

#             elements.append(Paragraph(f"Refund Receipt #{self.id}", title_style))
#             elements.append(Spacer(1, 0.5*cm))
#             elements.append(Paragraph("Praco Packaging Supplies Ltd.", bold_style))
#             elements.append(Spacer(1, 0.3*cm))
#             elements.append(HRFlowable(width=doc.width, thickness=1, color=colors.black))
#             elements.append(Spacer(1, 0.5*cm))

#             billing = self.billing_address
#             billing_address = "N/A"
#             billing_telephone = "N/A"
#             if billing:
#                 billing_address = f"{billing.first_name} {billing.last_name}<br/>{billing.street}<br/>{billing.city}, {billing.state} {billing.postal_code}<br/>{billing.country}"
#                 billing_telephone = billing.telephone_number or "N/A"
#             address_data = [
#                 [Paragraph("Bill To:", bold_style)],
#                 [Paragraph(billing_address, normal_style)],
#                 [Paragraph(f"Tel: {billing_telephone}", normal_style)]
#             ]
#             address_table = Table(address_data, colWidths=[16*cm])
#             address_table.setStyle(TableStyle([
#                 ('VALIGN', (0, 0), (-1, -1), 'TOP'),
#                 ('LEFTPADDING', (0, 0), (-1, -1), 0),
#                 ('RIGHTPADDING', (0, 0), (-1, -1), 0),
#             ]))
#             elements.append(address_table)
#             elements.append(Spacer(1, 0.5*cm))

#             refund_payment_receipt_link = self.refund_payment_receipt.url if self.refund_payment_receipt else "N/A"
#             total_due = self.calculate_total()
#             details_data = [
#                 [Paragraph("Date:", bold_style), Paragraph(self.updated_at.strftime('%d/%m/%Y'), normal_style)],
#                 [Paragraph("Refund Transaction ID:", bold_style), Paragraph(self.refund_transaction_id or "N/A", normal_style)],
#                 [Paragraph("Refund Payment Receipt:", bold_style), Paragraph(f'<a href="{refund_payment_receipt_link}">View Receipt</a>', orange_style)],
#                 [Paragraph("Total Refund:", bold_style), Paragraph(f"£{total_due:.2f}", orange_style)],
#             ]
#             if self.payment_method == 'stripe':
#                 transaction = self.transactions.first()
#                 if transaction:
#                     details_data.insert(1, [Paragraph("Payment Method:", bold_style), Paragraph("Stripe", normal_style)])
#             details_table = Table(details_data, colWidths=[4*cm, 12*cm])
#             details_table.setStyle(TableStyle([
#                 ('VALIGN', (0, 0), (-1, -1), 'TOP'),
#                 ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
#             ]))
#             elements.append(details_table)
#             elements.append(Spacer(1, 0.5*cm))

#             data = [['SKU', 'Packs', 'Units', 'Unit Price', 'Subtotal', 'Total']]
#             original_subtotal = Decimal('0.00')
#             items_exist = self.items.exists()
#             if items_exist:
#                 for item in self.items.all():
#                     try:
#                         original_item_subtotal = item.calculate_original_subtotal()
#                         item_subtotal = item.calculate_subtotal()
#                         pricing_data = PricingTierData.objects.filter(pricing_tier=item.pricing_tier, item=item.item).first()
#                         unit_price = pricing_data.price if pricing_data else Decimal('0.00')
#                         discount_percent = item.calculate_discount_percentage()
#                         original_subtotal += item_subtotal
#                         total_display = f"£{item_subtotal:.2f}"
#                         if discount_percent > 0:
#                             total_display += f"\n{discount_percent}% off"
                        
#                         units_per_pack = item.item.units_per_pack or 1
#                         total_units = item.pack_quantity * units_per_pack
                        
#                         data.append([
#                             item.item.sku or "N/A",
#                             str(item.pack_quantity),
#                             str(total_units),
#                             f"£{unit_price:.2f}",
#                             f"£{original_item_subtotal:.2f}",
#                             total_display
#                         ])
#                     except Exception as e:
#                         logger.error(f"Error processing item {item.id} for refund receipt: {str(e)}")
#                         data.append(["N/A", "Error", "0", "0", "£0.00", "£0.00"])
#             else:
#                 data.append(["N/A", "No items available", "0", "0", "£0.00", "£0.00"])
            
#             table = Table(data, colWidths=[3.5*cm, 3*cm, 2*cm, 2*cm, 2.5*cm, 2.5*cm])
#             table.setStyle(TableStyle([
#                 ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
#                 ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
#                 ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
#                 ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
#                 ('FONTSIZE', (0, 0), (-1, 0), 11),
#                 ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
#                 ('FONTSIZE', (0, 1), (-1, -1), 11),
#                 ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
#                 ('LEFTPADDING', (0, 0), (-1, -1), 5),
#                 ('RIGHTPADDING', (0, 0), (-1, -1), 5),
#             ]))
#             elements.append(table)
#             elements.append(Spacer(1, 0.5*cm))

#             subtotal = self.calculate_subtotal()
#             discount_amount = (subtotal * self.discount) / Decimal('100.00')
#             discounted_subtotal = subtotal - discount_amount
#             vat_amount = (discounted_subtotal * self.vat) / Decimal('100.00')
#             totals_data = [
#                 ['', 'Subtotal', f"£{subtotal:.2f}"],
#                 ['', f'Coupon Discount ({self.discount:.2f}%)', f"£{discount_amount:.2f}"],
#                 ['', f'VAT ({self.vat:.2f}%)', f"£{vat_amount:.2f}"],
#                 ['', 'Shipping Cost', f"£{self.shipping_cost:.2f}"],
#                 ['', 'Total', f"£{total_due:.2f}"]
#             ]
#             totals_table = Table(totals_data, colWidths=[9*cm, 3*cm, 3*cm])
#             totals_table.setStyle(TableStyle([
#                 ('ALIGN', (1, 0), (2, -1), 'RIGHT'),
#                 ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
#                 ('FONTSIZE', (0, 0), (-1, -1), 11),
#             ]))
#             elements.append(totals_table)
#             elements.append(Spacer(1, 0.5*cm))

#             elements.append(HRFlowable(width=doc.width, thickness=1, color=colors.black))
#             elements.append(Spacer(1, 0.5*cm))
#             footer = Paragraph(
#                 "Praco Packaging Supplies Ltd. | Account: 22035061 | Sort Code: 04-06-05 | VAT: 454687846",
#                 normal_style
#             )
#             elements.append(footer)

#             doc.build(elements)
#             buffer.seek(0)
#             logger.info(f"Successfully generated refund receipt PDF for order {self.id}")
#             return buffer
#         except Exception as e:
#             logger.error(f"Error generating refund receipt PDF for order {self.id}: {str(e)}")
#             return None

#     def generate_and_save_pdfs(self):
#         try:
#             items_exist = self.items.exists()
#             logger.info(f"Order {self.id} has items: {items_exist}")
#             if not items_exist:
#                 logger.warning(f"Skipping PDF generation for order {self.id} due to no items")
#                 return

#             self.update_order()

#             if not self.invoice:
#                 invoice_buffer = self.generate_invoice_pdf()
#                 if invoice_buffer:
#                     self.invoice.save(
#                         f'invoice_order_{self.id}.pdf',
#                         ContentFile(invoice_buffer.getvalue()),
#                         save=False
#                     )
#                     invoice_buffer.close()
#                     logger.info(f"Invoice PDF generated and saved for order {self.id} at {self.invoice.path}")
#                 else:
#                     logger.error(f"Invoice PDF generation failed for order {self.id}")

#             if not self.delivery_note:
#                 delivery_note_buffer = self.generate_delivery_note_pdf()
#                 if delivery_note_buffer:
#                     self.delivery_note.save(
#                         f'delivery_note_order_{self.id}.pdf',
#                         ContentFile(delivery_note_buffer.getvalue()),
#                         save=False
#                     )
#                     delivery_note_buffer.close()
#                     logger.info(f"Delivery note PDF generated and saved for order {self.id} at {self.delivery_note.path}")
#                 else:
#                     logger.error(f"Delivery note PDF generation failed for order {self.id}")

#             super(Order, self).save(update_fields=['invoice', 'delivery_note', 'discount'])
#             logger.info(f"Order {self.id} saved with updated invoice, delivery note, and discount fields")
#         except Exception as e:
#             logger.error(f"Error generating and saving PDFs for order {self.id}: {str(e)}")
#             raise

#     def generate_and_save_payment_receipts(self):
#         try:
#             update_fields = []
#             if self.payment_verified and self.payment_status == 'COMPLETED' and not self.paid_receipt:
#                 if not self.transaction_id:
#                     self.transaction_id = str(uuid.uuid4())
#                     update_fields.append('transaction_id')
#                 paid_receipt_buffer = self.generate_paid_receipt_pdf()
#                 if paid_receipt_buffer:
#                     self.paid_receipt.save(
#                         f'paid_receipt_order_{self.id}.pdf',
#                         ContentFile(paid_receipt_buffer.getvalue()),
#                         save=False
#                     )
#                     paid_receipt_buffer.close()
#                     update_fields.append('paid_receipt')
#                     logger.info(f"Paid receipt PDF generated and saved for order {self.id} at {self.paid_receipt.path}")
#                 else:
#                     logger.error(f"Paid receipt PDF generation failed for order {self.id}")

#             if self.payment_status == 'REFUND' and self.transaction_id and self.payment_receipt and self.refund_transaction_id and self.refund_payment_receipt and self.paid_receipt and not self.refund_receipt:
#                 refund_receipt_buffer = self.generate_refund_receipt_pdf()
#                 if refund_receipt_buffer:
#                     self.refund_receipt.save(
#                         f'refund_receipt_order_{self.id}.pdf',
#                         ContentFile(refund_receipt_buffer.getvalue()),
#                         save=False
#                     )
#                     refund_receipt_buffer.close()
#                     update_fields.append('refund_receipt')
#                     logger.info(f"Refund receipt PDF generated and saved for order {self.id} at {self.refund_receipt.path}")
#                 else:
#                     logger.error(f"Refund receipt PDF generation failed for order {self.id}")

#             if update_fields:
#                 super(Order, self).save(update_fields=update_fields)
#                 logger.info(f"Order {self.id} saved with updated fields: {update_fields}")
#         except Exception as e:
#             logger.error(f"Error generating and saving payment receipts for order {self.id}: {str(e)}")
#             raise

# @receiver(pre_save, sender=Order)
# def handle_payment_verified(sender, instance, **kwargs):
#     try:
#         if instance.id:
#             old_instance = Order.objects.get(id=instance.id)
#             if old_instance.payment_verified != instance.payment_verified:
#                 logger.info(f"Payment verified changed for order {instance.id} to {instance.payment_verified}")
#                 if instance.payment_verified:
#                     instance.payment_status = 'COMPLETED'
#                     if not instance.transaction_id:
#                         instance.transaction_id = str(uuid.uuid4())
#                     instance.generate_and_save_payment_receipts()
#                 else:
#                     instance.payment_status = 'PENDING'
#                     for field in ['paid_receipt', 'payment_receipt']:
#                         file_field = getattr(instance, field)
#                         if file_field:
#                             file_field.delete(save=False)
#                             setattr(instance, field, None)
#                     instance.transaction_id = None
#     except Exception as e:
#         logger.error(f"Error handling payment verified for order {instance.id}: {str(e)}")

# @receiver(post_save, sender=Order)
# def handle_order_creation(sender, instance, created, **kwargs):
#     if created:
#         logger.info(f"Order {instance.id} created, handling post-creation tasks")
#         try:
#             if instance.invoice and instance.user.email:
#                 user_name = instance.user.get_full_name() if hasattr(instance.user, 'get_full_name') else instance.user.username
#                 subject = f"Invoice for Order #{instance.id}"
#                 body = (
#                     f'<p>Dear {user_name},</p>'
#                     f'<p>Thank you for your purchase with Praco Packaging.</p>'
#                     f'<p>Please find attached the invoice for your order #{instance.id}.</p>'
#                 )
#                 attachments = [(f'invoice_order_{instance.id}.pdf', instance.invoice.read(), 'application/pdf')]
#                 success = send_email(subject, body, instance.user.email, is_html=True, attachments=attachments)
#                 if success:
#                     logger.info(f"Invoice email sent to {instance.user.email} for order {instance.id}")
#                 else:
#                     logger.error(f"Failed to send invoice email for order {instance.id}")
#         except Exception as e:
#             logger.error(f"Error sending invoice email for order {instance.id}: {str(e)}")

# @receiver(post_save, sender=Order)
# def handle_payment_status_change(sender, instance, **kwargs):
#     try:
#         if instance.id:
#             old_instance = Order.objects.get(id=instance.id)
#             if old_instance.payment_status != instance.payment_status:
#                 logger.info(f"Payment status changed for order {instance.id} to {instance.payment_status}")
#                 if instance.payment_status == 'COMPLETED':
#                     instance.generate_and_save_payment_receipts()
#                     if instance.delivery_note:
#                         subject = f"Delivery Note for Order #{instance.id}"
#                         body = (
#                             f'<p>Dear Team,</p>'
#                             f'<p>Please find attached the delivery note for order #{instance.id} from Praco Packaging.</p>'
#                             f'<p>For any inquiries, please contact our logistics team at <a href="mailto:logistics@pracopackaging.com" class="text-blue-600 hover:underline">logistics@pracopackaging.com</a>.</p>'
#                         )
#                         attachments = [(f'delivery_note_order_{instance.id}.pdf', instance.delivery_note.read(), 'application/pdf')]
#                         success = send_email(subject, body, 'siddiqui.faizmuhammad@gmail.com', is_html=True, attachments=attachments)
#                         if success:
#                             logger.info(f"Delivery note email sent to siddiqui.faizmuhammad@gmail.com for order {instance.id}")
#                         else:
#                             logger.error(f"Failed to send delivery note email for order {instance.id}")
#                 elif instance.payment_status == 'REFUND':
#                     instance.generate_and_save_payment_receipts()
#     except Exception as e:
#         logger.error(f"Error handling payment status change for order {instance.id}: {str(e)}")

class Order(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('SHIPPED', 'Shipped'),
        ('DELIVERED', 'Delivered'),
        ('CANCELLED', 'Cancelled'),
        ('RETURNED', 'Returned'),
    )
    PAYMENT_STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('REFUND', 'Refund'),
    )
    PAYMENT_METHOD_CHOICES = (
        ('manual_payment', 'Manual Payment'),
        ('stripe', 'Stripe Payment'),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    shipping_address = models.ForeignKey(
        Address, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='orders_as_shipping'
    )
    billing_address = models.ForeignKey(
        Address, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='orders_as_billing'
    )
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, editable=False)
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
        help_text="Discount percentage (e.g., 10 for 10%)."
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='PENDING')
    payment_verified = models.BooleanField(default=False)
    payment_method = models.CharField(
        max_length=50,
        choices=PAYMENT_METHOD_CHOICES,
        default='manual_payment'
    )
    transaction_id = models.CharField(max_length=100, blank=True, null=True)
    payment_receipt = models.FileField(upload_to='receipts/', blank=True, null=True)
    refund_transaction_id = models.CharField(max_length=100, blank=True, null=True)
    refund_payment_receipt = models.FileField(upload_to='refund_receipts/', blank=True, null=True)
    paid_receipt = models.FileField(upload_to='paid_receipts/', blank=True, null=True, editable=False)
    refund_receipt = models.FileField(upload_to='refund_receipts/', blank=True, null=True, editable=False)
    invoice = models.FileField(upload_to='invoices/', null=True, blank=True, editable=False)
    delivery_note = models.FileField(upload_to='delivery_notes/', null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['created_at']),
        ]
        verbose_name = 'order'
        verbose_name_plural = 'orders'

    def clean(self):
        errors = {}
        # Skip transaction_id and payment_receipt validations for Stripe payments
        if self.payment_method != 'stripe':
            if self.payment_verified:
                if not self.transaction_id:
                    errors['transaction_id'] = 'Transaction ID is required when payment is verified.'
                if not self.payment_receipt:
                    errors['payment_receipt'] = 'Payment receipt is required when payment is verified.'
                if self.payment_status in ['FAILED', 'PENDING']:
                    errors['payment_status'] = 'Payment status must be Completed/Refunded when payment is verified.'
            
            if self.payment_status == 'COMPLETED':
                if not self.transaction_id:
                    errors['transaction_id'] = 'Transaction ID is required when payment status is Completed.'
                if not self.payment_receipt:
                    errors['payment_receipt'] = 'Payment receipt is required when payment status is Completed.'
            
            elif self.payment_status == 'REFUND':
                if not self.transaction_id:
                    errors['transaction_id'] = 'Transaction ID is required when payment status is Refunded.'
                if not self.payment_receipt:
                    errors['payment_receipt'] = 'Payment receipt is required when payment status is Refunded.'
                if not self.refund_transaction_id:
                    errors['refund_transaction_id'] = 'Refunded transaction ID is required when payment status is Refunded.'
                if not self.refund_payment_receipt:
                    errors['refund_payment_receipt'] = 'Refunded payment receipt is required when payment status is Refunded.'

            for field, field_name in [(self.payment_receipt, 'payment_receipt'), (self.refund_payment_receipt, 'refund_payment_receipt')]:
                if field:
                    ext = field.name.lower().split('.')[-1]
                    if ext not in ['png', 'jpg', 'jpeg', 'pdf']:
                        errors[field_name] = 'File must be a PNG, JPG, or PDF.'

        if self.payment_status == 'REFUND' and not self.paid_receipt:
            errors['__all__'] = 'Paid receipt must exist when payment status is Refunded.'

        if errors:
            raise ValidationError(errors)

    def calculate_subtotal(self):
        try:
            total = Decimal('0.00')
            for item in self.items.all():
                item_subtotal = item.calculate_subtotal()
                total += item_subtotal
            logger.info(f"Order {self.id} subtotal: {total}")
            return total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except Exception as e:
            logger.error(f"Error calculating subtotal for order {self.id}: {str(e)}")
            return Decimal('0.00')

    def calculate_original_subtotal(self):
        try:
            total = self.calculate_subtotal()
            logger.info(f"Order {self.id} original subtotal: {total}")
            return total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except Exception as e:
            logger.error(f"Error calculating original subtotal for order {self.id}: {str(e)}")
            return Decimal('0.00')

    def calculate_total(self):
        try:
            subtotal = self.calculate_subtotal()
            discount_amount = (subtotal * self.discount) / Decimal('100.00')
            discounted_subtotal = subtotal - discount_amount
            vat_amount = (discounted_subtotal * self.vat) / Decimal('100.00')
            shipping_cost = Decimal(str(self.shipping_cost)).quantize(Decimal('0.01'))
            total = (discounted_subtotal + vat_amount + shipping_cost).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            logger.info(f"Order {self.id} total: {total} (subtotal={subtotal}, discount={self.discount}%, vat={self.vat}%, shipping={shipping_cost})")
            return total
        except Exception as e:
            logger.error(f"Error calculating total for order {self.id}: {str(e)}")
            return Decimal('0.00')

    def calculate_total_weight(self):
        try:
            total_weight = Decimal('0.00000000')
            for item in self.items.all():
                item_weight_kg = item.calculate_weight()
                total_units = item.total_units
                total_weight += item_weight_kg * Decimal(total_units)
            logger.info(f"Order {self.id} total weight: {total_weight}")
            return total_weight.quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)
        except Exception as e:
            logger.error(f"Error calculating total weight for order {self.id}: {str(e)}")
            return Decimal('0.00000000')

    def calculate_total_units_and_packs(self):
        try:
            total_units = 0
            total_packs = 0
            for item in self.items.all():
                units_per_pack = item.item.units_per_pack or 1
                total_units += item.pack_quantity * units_per_pack
                total_packs += item.pack_quantity
            logger.info(f"Order {self.id} total units: {total_units}, total packs: {total_packs}")
            return total_units, total_packs
        except Exception as e:
            logger.error(f"Error calculating units and packs for order {self.id}: {str(e)}")
            return 0, 0

    def update_order(self):
        try:
            self.calculate_total()
            super().save(update_fields=['discount'])
            logger.info(f"Updated order {self.id} calculations")
        except Exception as e:
            logger.error(f"Error updating order {self.id}: {str(e)}")

    def generate_invoice_pdf(self):
        try:
            buffer = BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
            elements = []
            styles = getSampleStyleSheet()
            normal_style = styles['Normal']
            normal_style.fontName = 'Helvetica'
            normal_style.fontSize = 11
            bold_style = ParagraphStyle(name='Bold', parent=normal_style, fontName='Helvetica-Bold')
            title_style = ParagraphStyle(name='Title', fontName='Helvetica-Bold', fontSize=14, textColor=colors.black)
            orange_style = ParagraphStyle(name='Orange', fontName='Helvetica-Bold', fontSize=12, textColor=HexColor('#F28C38'))
            small_style = ParagraphStyle(name='Small', fontName='Helvetica', fontSize=8)

            elements.append(Paragraph(f"Invoice #{self.id}", title_style))
            elements.append(Spacer(1, 0.5*cm))
            elements.append(Paragraph("Praco Packaging Supplies Ltd.", bold_style))
            elements.append(Spacer(1, 0.3*cm))
            elements.append(HRFlowable(width=doc.width, thickness=1, color=colors.black))
            elements.append(Spacer(1, 0.5*cm))

            shipping = self.shipping_address
            billing = self.billing_address
            shipping_address = billing_address = "N/A"
            shipping_telephone = billing_telephone = "N/A"
            if shipping:
                shipping_address = f"{shipping.first_name} {shipping.last_name}<br/>{shipping.street}<br/>{shipping.city}, {shipping.state} {shipping.postal_code}<br/>{shipping.country}"
                shipping_telephone = shipping.telephone_number or "N/A"
            if billing:
                billing_address = f"{billing.first_name} {billing.last_name}<br/>{billing.street}<br/>{billing.city}, {billing.state} {billing.postal_code}<br/>{billing.country}"
                billing_telephone = billing.telephone_number or "N/A"
            address_data = [
                [Paragraph("Bill To:", bold_style), Paragraph("Ship To:", bold_style)],
                [Paragraph(billing_address, normal_style), Paragraph(shipping_address, normal_style)],
                [Paragraph(f"Tel: {billing_telephone}", normal_style), Paragraph(f"Tel: {shipping_telephone}", normal_style)]
            ]
            address_table = Table(address_data, colWidths=[8*cm, 8*cm])
            address_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ]))
            elements.append(address_table)
            elements.append(Spacer(1, 0.5*cm))

            total_weight = self.calculate_total_weight()
            due_date = self.created_at + timedelta(days=14)
            total_due = self.calculate_total()
            details_data = [
                [Paragraph("Date:", bold_style), Paragraph(self.created_at.strftime('%d/%m/%Y'), normal_style)],
                [Paragraph("Due Date:", bold_style), Paragraph(due_date.strftime('%d/%m/%Y'), normal_style)],
                [Paragraph("Total Weight:", bold_style), Paragraph(f"{total_weight:.3f} kg", normal_style)],
                [Paragraph("Total Due:", bold_style), Paragraph(f"£{total_due:.2f}", orange_style)]
            ]
            if self.payment_method == 'stripe':
                transaction = self.transactions.first()
                details_data.append([Paragraph("Payment Method:", bold_style), Paragraph("Stripe", normal_style)])
                if transaction:
                    details_data.append([Paragraph("Transaction ID:", bold_style), Paragraph(transaction.stripe_payment_intent_id, normal_style)])
            details_table = Table(details_data, colWidths=[4*cm, 12*cm])
            details_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ]))
            elements.append(details_table)
            elements.append(Spacer(1, 0.5*cm))

            data = [['SKU', 'Boxes', 'Units', 'Unit Price', 'Subtotal', 'Total']]
            original_subtotal = Decimal('0.00')
            items_exist = self.items.exists()
            logger.info(f"Order {self.id} has items: {items_exist}")
            if items_exist:
                for item in self.items.all():
                    try:
                        original_item_subtotal = item.calculate_original_subtotal()
                        item_subtotal = item.calculate_subtotal()
                        pricing_data = PricingTierData.objects.filter(pricing_tier=item.pricing_tier, item=item.item).first()
                        unit_price = pricing_data.price if pricing_data else Decimal('0.00')
                        discount_percent = item.calculate_discount_percentage()
                        original_subtotal += item_subtotal
                        total_display = f"£{item_subtotal:.2f}"
                        if discount_percent > 0:
                            total_display += f"\n{discount_percent}% off"
                        
                        units_per_pack = item.item.units_per_pack or 1
                        total_units = item.pack_quantity * units_per_pack
                        
                        data.append([
                            item.item.sku or "N/A",
                            str(item.pack_quantity),
                            str(total_units),
                            f"£{unit_price:.2f}",
                            f"£{original_item_subtotal:.2f}",
                            total_display
                        ])
                    except Exception as e:
                        logger.error(f"Error processing item {item.id} for invoice: {str(e)}")
                        data.append(["N/A", "Error", "0", "0", "£0.00", "£0.00"])
            else:
                logger.warning(f"No items found for order {self.id}")
                data.append(["N/A", "No items available", "0", "0", "£0.00", "£0.00"])
            
            table = Table(data, colWidths=[3.5*cm, 2.5*cm, 2*cm, 2.5*cm, 2.5*cm, 2.5*cm])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 11),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                ('LEFTPADDING', (0, 0), (-1, -1), 5),
                ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ]))
            elements.append(table)
            elements.append(Spacer(1, 0.5*cm))

            subtotal = self.calculate_subtotal()
            discount_amount = (subtotal * self.discount) / Decimal('100.00')
            discounted_subtotal = subtotal - discount_amount
            vat_amount = (discounted_subtotal * self.vat) / Decimal('100.00')
            totals_data = [
                ['', 'Subtotal', f"£{subtotal:.2f}"],
                ['', f'Coupon Discount ({self.discount:.2f}%)', f"£{discount_amount:.2f}"],
                ['', f'VAT ({self.vat:.2f}%)', f"£{vat_amount:.2f}"],
                ['', 'Shipping Cost', f"£{self.shipping_cost:.2f}"],
                ['', 'Total', f"£{total_due:.2f}"]
            ]
            totals_table = Table(totals_data, colWidths=[9*cm, 3*cm, 3*cm])
            totals_table.setStyle(TableStyle([
                ('ALIGN', (1, 0), (2, -1), 'RIGHT'),
                ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 11),
            ]))
            elements.append(totals_table)
            elements.append(Spacer(1, 0.5*cm))

            notes = Paragraph(
                "Notes: 7-day exchange or refund policy for damaged goods. Contact us within 7 days for assistance. A 3% fee applies to cash payments.",
                small_style
            )
            elements.append(notes)
            elements.append(Spacer(1, 0.5*cm))
            elements.append(HRFlowable(width=doc.width, thickness=1, color=colors.black))
            elements.append(Spacer(1, 0.5*cm))
            footer = Paragraph(
                "Praco Packaging Supplies Ltd. | Account: 22035061 | Sort Code: 04-06-05 | VAT: 454687846",
                normal_style
            )
            elements.append(footer)

            doc.build(elements)
            buffer.seek(0)
            logger.info(f"Successfully generated invoice PDF for order {self.id}")
            return buffer
        except Exception as e:
            logger.error(f"Error generating invoice PDF for order {self.id}: {str(e)}")
            return None

    def generate_delivery_note_pdf(self):
        try:
            buffer = BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
            elements = []
            styles = getSampleStyleSheet()
            normal_style = styles['Normal']
            normal_style.fontName = 'Helvetica'
            normal_style.fontSize = 11
            bold_style = ParagraphStyle(name='Bold', parent=normal_style, fontName='Helvetica-Bold')
            title_style = ParagraphStyle(name='Title', fontName='Helvetica-Bold', fontSize=14, textColor=colors.black)
            small_style = ParagraphStyle(name='Small', fontName='Helvetica', fontSize=8)

            elements.append(Paragraph(f"Delivery Note #{self.id}", title_style))
            elements.append(Spacer(1, 0.5*cm))
            elements.append(Paragraph("Praco Packaging Supplies Ltd.", bold_style))
            elements.append(Spacer(1, 0.3*cm))
            elements.append(HRFlowable(width=doc.width, thickness=1, color=colors.black))
            elements.append(Spacer(1, 0.5*cm))

            shipping = self.shipping_address
            shipping_address = "N/A"
            shipping_telephone = "N/A"
            if shipping:
                shipping_address = f"{shipping.first_name} {shipping.last_name}<br/>{shipping.street}<br/>{shipping.city}, {shipping.state} {shipping.postal_code}<br/>{shipping.country}"
                shipping_telephone = shipping.telephone_number or "N/A"
            address_data = [
                [Paragraph("Ship To:", bold_style)],
                [Paragraph(shipping_address, normal_style)],
                [Paragraph(f"Tel: {shipping_telephone}", normal_style)]
            ]
            address_table = Table(address_data, colWidths=[16*cm])
            address_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ]))
            elements.append(address_table)
            elements.append(Spacer(1, 0.5*cm))

            total_weight = self.calculate_total_weight()
            details_data = [
                [Paragraph("Date:", bold_style), Paragraph(self.created_at.strftime('%d/%m/%Y'), normal_style)],
                [Paragraph("Total Weight:", bold_style), Paragraph(f"{total_weight:.3f} kg", normal_style)],
            ]
            if self.payment_method == 'stripe':
                transaction = self.transactions.first()
                if transaction:
                    details_data.append([Paragraph("Transaction ID:", bold_style), Paragraph(transaction.stripe_payment_intent_id, normal_style)])
            details_table = Table(details_data, colWidths=[4*cm, 12*cm])
            details_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ]))
            elements.append(details_table)
            elements.append(Spacer(1, 0.5*cm))

            data = [['SKU', 'Packs', 'Units', 'Total Units']]
            items_exist = self.items.exists()
            logger.info(f"Order {self.id} has items for delivery note: {items_exist}")
            if items_exist:
                for item in self.items.all():
                    try:
                        units_per_pack = item.item.units_per_pack or 1
                        total_units = item.pack_quantity * units_per_pack
                        data.append([
                            item.item.sku or "N/A",
                            str(item.pack_quantity),
                            str(total_units),
                            str(item.total_units)
                        ])
                    except Exception as e:
                        logger.error(f"Error processing item {item.id} for delivery note: {str(e)}")
                        data.append(["N/A", "Error", "0", "0"])
            else:
                logger.warning(f"No items found for order {self.id}")
                data.append(["N/A", "No items available", "0", "0"])
            
            table = Table(data, colWidths=[3.5*cm, 5*cm, 2*cm, 2*cm])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 11),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                ('LEFTPADDING', (0, 0), (-1, -1), 5),
                ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ]))
            elements.append(table)
            elements.append(Spacer(1, 0.5*cm))

            elements.append(HRFlowable(width=doc.width, thickness=1, color=colors.black))
            elements.append(Spacer(1, 0.5*cm))
            footer = Paragraph(
                "Praco Packaging Supplies Ltd. | Account: 22035061 | Sort Code: 04-06-05 | VAT: 454687846",
                normal_style
            )
            elements.append(footer)

            doc.build(elements)
            buffer.seek(0)
            logger.info(f"Successfully generated delivery note PDF for order {self.id}")
            return buffer
        except Exception as e:
            logger.error(f"Error generating delivery note PDF for order {self.id}: {str(e)}")
            return None

    def generate_paid_receipt_pdf(self):
        try:
            buffer = BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
            elements = []
            styles = getSampleStyleSheet()
            normal_style = styles['Normal']
            normal_style.fontName = 'Helvetica'
            normal_style.fontSize = 11
            bold_style = ParagraphStyle(name='Bold', parent=normal_style, fontName='Helvetica-Bold')
            title_style = ParagraphStyle(name='Title', fontName='Helvetica-Bold', fontSize=14, textColor=colors.black)
            orange_style = ParagraphStyle(name='Orange', fontName='Helvetica-Bold', fontSize=12, textColor=HexColor('#F28C38'))
            stamp_style = ParagraphStyle(name='Stamp', fontName='Helvetica-Bold', fontSize=24, textColor=colors.green)

            elements.append(Paragraph("PAID", stamp_style))
            elements.append(Spacer(1, 0.5*cm))

            elements.append(Paragraph(f"Paid Receipt #{self.id}", title_style))
            elements.append(Spacer(1, 0.5*cm))
            elements.append(Paragraph("Praco Packaging Supplies Ltd.", bold_style))
            elements.append(Spacer(1, 0.3*cm))
            elements.append(HRFlowable(width=doc.width, thickness=1, color=colors.black))
            elements.append(Spacer(1, 0.5*cm))

            billing = self.billing_address
            billing_address = "N/A"
            billing_telephone = "N/A"
            if billing:
                billing_address = f"{billing.first_name} {billing.last_name}<br/>{billing.street}<br/>{billing.city}, {billing.state} {billing.postal_code}<br/>{billing.country}"
                billing_telephone = billing.telephone_number or "N/A"
            address_data = [
                [Paragraph("Bill To:", bold_style)],
                [Paragraph(billing_address, normal_style)],
                [Paragraph(f"Tel: {billing_telephone}", normal_style)]
            ]
            address_table = Table(address_data, colWidths=[16*cm])
            address_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ]))
            elements.append(address_table)
            elements.append(Spacer(1, 0.5*cm))

            payment_receipt_link = self.payment_receipt.url if self.payment_receipt else "N/A"
            total_due = self.calculate_total()
            details_data = [
                [Paragraph("Date:", bold_style), Paragraph(self.updated_at.strftime('%d/%m/%Y'), normal_style)],
                [Paragraph("Transaction ID:", bold_style), Paragraph(self.transaction_id or "N/A", normal_style)],
                [Paragraph("Total Paid:", bold_style), Paragraph(f"£{total_due:.2f}", orange_style)],
            ]
            if self.payment_method == 'manual_payment' and self.payment_receipt:
                details_data.insert(2, [Paragraph("Payment Receipt:", bold_style), Paragraph(f'<a href="{payment_receipt_link}">View Receipt</a>', orange_style)])
            if self.payment_method == 'stripe':
                transaction = self.transactions.first()
                if transaction:
                    details_data.insert(1, [Paragraph("Payment Method:", bold_style), Paragraph("Stripe", normal_style)])


            details_table = Table(details_data, colWidths=[4*cm, 12*cm])
            details_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ]))
            elements.append(details_table)
            elements.append(Spacer(1, 0.5*cm))

            data = [['SKU', 'Boxes', 'Units', 'Unit Price', 'Subtotal', 'Total']]
            original_subtotal = Decimal('0.00')
            items_exist = self.items.exists()
            if items_exist:
                for item in self.items.all():
                    try:
                        original_item_subtotal = item.calculate_original_subtotal()
                        item_subtotal = item.calculate_subtotal()
                        pricing_data = PricingTierData.objects.filter(pricing_tier=item.pricing_tier, item=item.item).first()
                        unit_price = pricing_data.price if pricing_data else Decimal('0.00')
                        discount_percent = item.calculate_discount_percentage()
                        original_subtotal += item_subtotal
                        total_display = f"£{item_subtotal:.2f}"
                        if discount_percent > 0:
                            total_display += f"\n{discount_percent}% off"
                        
                        units_per_pack = item.item.units_per_pack or 1
                        total_units = item.pack_quantity * units_per_pack
                        
                        data.append([
                            item.item.sku or "N/A",
                            str(item.pack_quantity),
                            str(total_units),
                            f"£{unit_price:.2f}",
                            f"£{original_item_subtotal:.2f}",
                            total_display
                        ])
                    except Exception as e:
                        logger.error(f"Error processing item {item.id} for paid receipt: {str(e)}")
                        data.append(["N/A", "Error", "0", "0", "£0.00", "£0.00"])
            else:
                data.append(["N/A", "No items available", "0", "0", "£0.00", "£0.00"])
            
            table = Table(data, colWidths=[3.5*cm, 2.5*cm, 2*cm, 2.5*cm, 2.5*cm, 2.5*cm])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 11),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                ('LEFTPADDING', (0, 0), (-1, -1), 5),
                ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ]))
            elements.append(table)
            elements.append(Spacer(1, 0.5*cm))

            subtotal = self.calculate_subtotal()
            discount_amount = (subtotal * self.discount) / Decimal('100.00')
            discounted_subtotal = subtotal - discount_amount
            vat_amount = (discounted_subtotal * self.vat) / Decimal('100.00')
            totals_data = [
                ['', 'Subtotal', f"£{subtotal:.2f}"],
                ['', f'Coupon Discount ({self.discount:.2f}%)', f"£{discount_amount:.2f}"],
                ['', f'VAT ({self.vat:.2f}%)', f"£{vat_amount:.2f}"],
                ['', 'Shipping Cost', f"£{self.shipping_cost:.2f}"],
                ['', 'Total', f"£{total_due:.2f}"]
            ]
            totals_table = Table(totals_data, colWidths=[9*cm, 3*cm, 3*cm])
            totals_table.setStyle(TableStyle([
                ('ALIGN', (1, 0), (2, -1), 'RIGHT'),
                ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 11),
            ]))
            elements.append(totals_table)
            elements.append(Spacer(1, 0.5*cm))

            elements.append(HRFlowable(width=doc.width, thickness=1, color=colors.black))
            elements.append(Spacer(1, 0.5*cm))
            footer = Paragraph(
                "Praco Packaging Supplies Ltd. | Account: 22035061 | Sort Code: 04-06-05 | VAT: 454687846",
                normal_style
            )
            elements.append(footer)

            doc.build(elements)
            buffer.seek(0)
            logger.info(f"Successfully generated paid receipt PDF for order {self.id}")
            return buffer
        except Exception as e:
            logger.error(f"Error generating paid receipt PDF for order {self.id}: {str(e)}")
            return None

    def generate_refund_receipt_pdf(self):
        try:
            buffer = BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
            elements = []
            styles = getSampleStyleSheet()
            normal_style = styles['Normal']
            normal_style.fontName = 'Helvetica'
            normal_style.fontSize = 11
            bold_style = ParagraphStyle(name='Bold', parent=normal_style, fontName='Helvetica-Bold')
            title_style = ParagraphStyle(name='Title', fontName='Helvetica-Bold', fontSize=14, textColor=colors.black)
            orange_style = ParagraphStyle(name='Orange', fontName='Helvetica-Bold', fontSize=12, textColor=HexColor('#F28C38'))
            stamp_style = ParagraphStyle(name='Stamp', fontName='Helvetica-Bold', fontSize=24, textColor=colors.red)

            elements.append(Paragraph("REFUND", stamp_style))
            elements.append(Spacer(1, 0.5*cm))

            elements.append(Paragraph(f"Refund Receipt #{self.id}", title_style))
            elements.append(Spacer(1, 0.5*cm))
            elements.append(Paragraph("Praco Packaging Supplies Ltd.", bold_style))
            elements.append(Spacer(1, 0.3*cm))
            elements.append(HRFlowable(width=doc.width, thickness=1, color=colors.black))
            elements.append(Spacer(1, 0.5*cm))

            billing = self.billing_address
            billing_address = "N/A"
            billing_telephone = "N/A"
            if billing:
                billing_address = f"{billing.first_name} {billing.last_name}<br/>{billing.street}<br/>{billing.city}, {billing.state} {billing.postal_code}<br/>{billing.country}"
                billing_telephone = billing.telephone_number or "N/A"
            address_data = [
                [Paragraph("Bill To:", bold_style)],
                [Paragraph(billing_address, normal_style)],
                [Paragraph(f"Tel: {billing_telephone}", normal_style)]
            ]
            address_table = Table(address_data, colWidths=[16*cm])
            address_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ]))
            elements.append(address_table)
            elements.append(Spacer(1, 0.5*cm))

            refund_payment_receipt_link = self.refund_payment_receipt.url if self.refund_payment_receipt else "N/A"
            total_due = self.calculate_total()
            details_data = [
                [Paragraph("Date:", bold_style), Paragraph(self.updated_at.strftime('%d/%m/%Y'), normal_style)],
                [Paragraph("Refund Transaction ID:", bold_style), Paragraph(self.refund_transaction_id or "N/A", normal_style)],
                [Paragraph("Refund Payment Receipt:", bold_style), Paragraph(f'<a href="{refund_payment_receipt_link}">View Receipt</a>', orange_style)],
                [Paragraph("Total Refund:", bold_style), Paragraph(f"£{total_due:.2f}", orange_style)],
            ]
            if self.payment_method == 'stripe':
                transaction = self.transactions.first()
                if transaction:
                    details_data.insert(1, [Paragraph("Payment Method:", bold_style), Paragraph("Stripe", normal_style)])
            details_table = Table(details_data, colWidths=[4*cm, 12*cm])
            details_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ]))
            elements.append(details_table)
            elements.append(Spacer(1, 0.5*cm))

            data = [['SKU', 'Boxes', 'Units', 'Unit Price', 'Subtotal', 'Total']]
            original_subtotal = Decimal('0.00')
            items_exist = self.items.exists()
            if items_exist:
                for item in self.items.all():
                    try:
                        original_item_subtotal = item.calculate_original_subtotal()
                        item_subtotal = item.calculate_subtotal()
                        pricing_data = PricingTierData.objects.filter(pricing_tier=item.pricing_tier, item=item.item).first()
                        unit_price = pricing_data.price if pricing_data else Decimal('0.00')
                        discount_percent = item.calculate_discount_percentage()
                        original_subtotal += item_subtotal
                        total_display = f"£{item_subtotal:.2f}"
                        if discount_percent > 0:
                            total_display += f"\n{discount_percent}% off"
                        
                        units_per_pack = item.item.units_per_pack or 1
                        total_units = item.pack_quantity * units_per_pack
                        
                        data.append([
                            item.item.sku or "N/A",
                            str(item.pack_quantity),
                            str(total_units),
                            f"£{unit_price:.2f}",
                            f"£{original_item_subtotal:.2f}",
                            total_display
                        ])
                    except Exception as e:
                        logger.error(f"Error processing item {item.id} for refund receipt: {str(e)}")
                        data.append(["N/A", "Error", "0", "0", "£0.00", "£0.00"])
            else:
                data.append(["N/A", "No items available", "0", "0", "£0.00", "£0.00"])
            
            table = Table(data, colWidths=[3.5*cm, 2.5*cm, 2*cm, 2.5*cm, 2.5*cm, 2.5*cm])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 11),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                ('LEFTPADDING', (0, 0), (-1, -1), 5),
                ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ]))
            elements.append(table)
            elements.append(Spacer(1, 0.5*cm))

            subtotal = self.calculate_subtotal()
            discount_amount = (subtotal * self.discount) / Decimal('100.00')
            discounted_subtotal = subtotal - discount_amount
            vat_amount = (discounted_subtotal * self.vat) / Decimal('100.00')
            totals_data = [
                ['', 'Subtotal', f"£{subtotal:.2f}"],
                ['', f'Coupon Discount ({self.discount:.2f}%)', f"£{discount_amount:.2f}"],
                ['', f'VAT ({self.vat:.2f}%)', f"£{vat_amount:.2f}"],
                ['', 'Shipping Cost', f"£{self.shipping_cost:.2f}"],
                ['', 'Total', f"£{total_due:.2f}"]
            ]
            totals_table = Table(totals_data, colWidths=[9*cm, 3*cm, 3*cm])
            totals_table.setStyle(TableStyle([
                ('ALIGN', (1, 0), (2, -1), 'RIGHT'),
                ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 11),
            ]))
            elements.append(totals_table)
            elements.append(Spacer(1, 0.5*cm))

            elements.append(HRFlowable(width=doc.width, thickness=1, color=colors.black))
            elements.append(Spacer(1, 0.5*cm))
            footer = Paragraph(
                "Praco Packaging Supplies Ltd. | Account: 22035061 | Sort Code: 04-06-05 | VAT: 454687846",
                normal_style
            )
            elements.append(footer)

            doc.build(elements)
            buffer.seek(0)
            logger.info(f"Successfully generated refund receipt PDF for order {self.id}")
            return buffer
        except Exception as e:
            logger.error(f"Error generating refund receipt PDF for order {self.id}: {str(e)}")
            return None

    def generate_and_save_pdfs(self):
        try:
            items_exist = self.items.exists()
            logger.info(f"Order {self.id} has items: {items_exist}")
            if not items_exist:
                logger.warning(f"Skipping PDF generation for order {self.id} due to no items")
                return

            self.update_order()

            if not self.invoice:
                invoice_buffer = self.generate_invoice_pdf()
                if invoice_buffer:
                    self.invoice.save(
                        f'invoice_order_{self.id}.pdf',
                        ContentFile(invoice_buffer.getvalue()),
                        save=False
                    )
                    invoice_buffer.close()
                    logger.info(f"Invoice PDF generated and saved for order {self.id} at {self.invoice.path}")
                else:
                    logger.error(f"Invoice PDF generation failed for order {self.id}")

            if not self.delivery_note:
                delivery_note_buffer = self.generate_delivery_note_pdf()
                if delivery_note_buffer:
                    self.delivery_note.save(
                        f'delivery_note_order_{self.id}.pdf',
                        ContentFile(delivery_note_buffer.getvalue()),
                        save=False
                    )
                    delivery_note_buffer.close()
                    logger.info(f"Delivery note PDF generated and saved for order {self.id} at {self.delivery_note.path}")
                else:
                    logger.error(f"Delivery note PDF generation failed for order {self.id}")

            super(Order, self).save(update_fields=['invoice', 'delivery_note', 'discount'])
            logger.info(f"Order {self.id} saved with updated invoice, delivery note, and discount fields")
        except Exception as e:
            logger.error(f"Error generating and saving PDFs for order {self.id}: {str(e)}")
            raise

    def generate_and_save_payment_receipts(self):
        try:
            update_fields = []
            if self.payment_verified and self.payment_status == 'COMPLETED' and not self.paid_receipt:
                if self.payment_method == 'stripe':
                    # For Stripe, use transaction.stripe_payment_intent_id if available
                    transaction = self.transactions.first()
                    if transaction and transaction.stripe_payment_intent_id and not self.transaction_id:
                        self.transaction_id = transaction.stripe_payment_intent_id
                        update_fields.append('transaction_id')
                elif not self.transaction_id:
                    # For manual payments, generate a UUID if no transaction_id
                    self.transaction_id = str(uuid.uuid4())
                    update_fields.append('transaction_id')
                
                paid_receipt_buffer = self.generate_paid_receipt_pdf()
                if paid_receipt_buffer:
                    self.paid_receipt.save(
                        f'paid_receipt_order_{self.id}.pdf',
                        ContentFile(paid_receipt_buffer.getvalue()),
                        save=False
                    )
                    paid_receipt_buffer.close()
                    update_fields.append('paid_receipt')
                    logger.info(f"Paid receipt PDF generated and saved for order {self.id} at {self.paid_receipt.path}")
                else:
                    logger.error(f"Paid receipt PDF generation failed for order {self.id}")

            if self.payment_status == 'REFUND' and self.transaction_id and self.refund_transaction_id and self.paid_receipt and not self.refund_receipt:
                if self.payment_method != 'stripe' and not self.payment_receipt:
                    logger.error(f"Payment receipt required for refund with manual payment for order {self.id}")
                    return
                if self.payment_method != 'stripe' and not self.refund_payment_receipt:
                    logger.error(f"Refund payment receipt required for refund with manual payment for order {self.id}")
                    return
                refund_receipt_buffer = self.generate_refund_receipt_pdf()
                if refund_receipt_buffer:
                    self.refund_receipt.save(
                        f'refund_receipt_order_{self.id}.pdf',
                        ContentFile(refund_receipt_buffer.getvalue()),
                        save=False
                    )
                    refund_receipt_buffer.close()
                    update_fields.append('refund_receipt')
                    logger.info(f"Refund receipt PDF generated and saved for order {self.id} at {self.refund_receipt.path}")
                else:
                    logger.error(f"Refund receipt PDF generation failed for order {self.id}")

            if update_fields:
                super(Order, self).save(update_fields=update_fields)
                logger.info(f"Order {self.id} saved with updated fields: {update_fields}")
        except Exception as e:
            logger.error(f"Error generating and saving payment receipts for order {self.id}: {str(e)}")
            raise

@receiver(pre_save, sender=Order)
def handle_payment_verified(sender, instance, **kwargs):
    try:
        if instance.id:
            old_instance = Order.objects.get(id=instance.id)
            if old_instance.payment_verified != instance.payment_verified:
                logger.info(f"Payment verified changed for order {instance.id} to {instance.payment_verified}")
                if instance.payment_verified:
                    instance.payment_status = 'COMPLETED'
                    if instance.payment_method == 'stripe':
                        # Set transaction_id from Transaction model for Stripe
                        transaction = instance.transactions.first()
                        if transaction and transaction.stripe_payment_intent_id:
                            instance.transaction_id = transaction.stripe_payment_intent_id
                    elif not instance.transaction_id:
                        # Generate UUID for manual payments
                        instance.transaction_id = str(uuid.uuid4())
                    instance.generate_and_save_payment_receipts()
                else:
                    instance.payment_status = 'PENDING'
                    if instance.payment_method != 'stripe':
                        # Only clear payment_receipt for non-Stripe payments
                        for field in ['paid_receipt', 'payment_receipt']:
                            file_field = getattr(instance, field)
                            if file_field:
                                file_field.delete(save=False)
                                setattr(instance, field, None)
                    instance.transaction_id = None
    except Exception as e:
        logger.error(f"Error handling payment verified for order {instance.id}: {str(e)}")

@receiver(post_save, sender=Order)
def handle_order_creation(sender, instance, created, **kwargs):
    if created:
        logger.info(f"Order {instance.id} created, handling post-creation tasks")
        try:
            if instance.invoice and instance.user.email:
                user_name = instance.user.get_full_name() if hasattr(instance.user, 'get_full_name') else instance.user.username
                subject = f"Invoice for Order #{instance.id}"
                body = (
                    f'<p>Dear {user_name},</p>'
                    f'<p>Thank you for your purchase with Praco Packaging.</p>'
                    f'<p>Please find attached the invoice for your order #{instance.id}.</p>'
                )
                attachments = [(f'invoice_order_{instance.id}.pdf', instance.invoice.read(), 'application/pdf')]
                success = send_email(subject, body, instance.user.email, is_html=True, attachments=attachments)
                if success:
                    logger.info(f"Invoice email sent to {instance.user.email} for order {instance.id}")
                else:
                    logger.error(f"Failed to send invoice email for order {instance.id}")
        except Exception as e:
            logger.error(f"Error sending invoice email for order {instance.id}: {str(e)}")

@receiver(post_save, sender=Order)
def handle_payment_status_change(sender, instance, **kwargs):
    try:
        if instance.id:
            old_instance = Order.objects.get(id=instance.id)
            if old_instance.payment_status != instance.payment_status:
                logger.info(f"Payment status changed for order {instance.id} to {instance.payment_status}")
                if instance.payment_status == 'COMPLETED':
                    if instance.payment_method == 'stripe':
                        # Set transaction_id from Transaction model for Stripe
                        transaction = instance.transactions.first()
                        if transaction and transaction.stripe_payment_intent_id and not instance.transaction_id:
                            instance.transaction_id = transaction.stripe_payment_intent_id
                            instance.save(update_fields=['transaction_id'])
                    instance.generate_and_save_payment_receipts()
                    if instance.delivery_note:
                        subject = f"Delivery Note for Order #{instance.id}"
                        body = (
                            f'<p>Dear Team,</p>'
                            f'<p>Please find attached the delivery note for order #{instance.id} from Praco Packaging.</p>'
                            f'<p>For any inquiries, please contact our logistics team at <a href="mailto:logistics@pracopackaging.com" class="text-blue-600 hover:underline">logistics@pracopackaging.com</a>.</p>'
                        )
                        attachments = [(f'delivery_note_order_{instance.id}.pdf', instance.delivery_note.read(), 'application/pdf')]
                        success = send_email(subject, body, 'siddiqui.faizmuhammad@gmail.com', is_html=True, attachments=attachments)
                        if success:
                            logger.info(f"Delivery note email sent to siddiqui.faizmuhammad@gmail.com for order {instance.id}")
                        else:
                            logger.error(f"Failed to send delivery note email for order {instance.id}")
                elif instance.payment_status == 'REFUND':
                    instance.generate_and_save_payment_receipts()
    except Exception as e:
        logger.error(f"Error handling payment status change for order {instance.id}: {str(e)}")

class OrderItem(models.Model):
    order = models.ForeignKey('Order', on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey('Item', on_delete=models.PROTECT, related_name='order_items')
    pricing_tier = models.ForeignKey('PricingTier', on_delete=models.PROTECT, related_name='order_items')
    pack_quantity = models.PositiveIntegerField()
    unit_type = models.CharField(
        max_length=10,
        choices=(('pack', 'Pack'),),
        default='pack',
        editable=False,
        help_text="Unit type is fixed to 'pack'."
    )
    user_exclusive_price = models.ForeignKey(
        'UserExclusivePrice',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orderitem_items'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['order', 'item']),
            models.Index(fields=['pricing_tier']),
            models.Index(fields=['created_at']),
        ]
        unique_together = ('order', 'item', 'pricing_tier', 'pack_quantity', 'unit_type')
        verbose_name = 'order item'
        verbose_name_plural = 'order items'

    def calculate_weight(self):
        """Calculate the weight per unit."""
        try:
            if not self.item:
                return Decimal('0.00000000')
            weight = self.item.weight or Decimal('0.00000000')
            weight_unit = self.item.weight_unit or 'kg'
            return self.convert_weight_to_kg(weight, weight_unit)
        except Exception as e:
            logger.error(f"Error calculating weight for order item {self.id}: {str(e)}")
            return Decimal('0.00000000')

    def calculate_discount_percentage(self):
        """Calculate the discount percentage from UserExclusivePrice."""
        try:
            if self.user_exclusive_price and hasattr(self.user_exclusive_price, 'discount_percentage'):
                return self.user_exclusive_price.discount_percentage.quantize(Decimal('0.01'))
            return Decimal('0.00')
        except Exception as e:
            logger.error(f"Error calculating discount percentage for order item {self.id}: {str(e)}")
            return Decimal('0.00')

    def convert_weight_to_kg(self, weight, weight_unit):
        """Convert weight to kilograms."""
        try:
            if weight is None or weight_unit is None:
                return Decimal('0.00000000')
            weight = Decimal(str(weight))
            if weight_unit == 'lb':
                return (weight * Decimal('0.453592')).quantize(Decimal('0.00000001'))
            elif weight_unit == 'oz':
                return (weight * Decimal('0.0283495')).quantize(Decimal('0.00000001'))
            elif weight_unit == 'g':
                return (weight * Decimal('0.001')).quantize(Decimal('0.00000001'))
            elif weight_unit == 'kg':
                return weight.quantize(Decimal('0.00000001'))
            return Decimal('0.00000000')
        except Exception as e:
            logger.error(f"Error converting weight for order item {self.id}: {str(e)}")
            return Decimal('0.00000000')

    @property
    def total_units(self):
        """Calculate total units for the item."""
        try:
            if not self.item:
                return 0
            units_per_pack = self.item.units_per_pack or 1
            return self.pack_quantity * units_per_pack
        except Exception as e:
            logger.error(f"Error calculating total units for order item {self.id}: {str(e)}")
            return 0

    def calculate_original_subtotal(self):
        """Calculate original subtotal, without UserExclusivePrice discounts."""
        try:
            pricing_data = PricingTierData.objects.filter(
                pricing_tier=self.pricing_tier, item=self.item
            ).first()
            if pricing_data and self.item:
                units_per_pack = self.item.units_per_pack or 1
                per_pack_price = pricing_data.price * Decimal(units_per_pack)
                item_subtotal = per_pack_price * Decimal(self.pack_quantity)
                return item_subtotal.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            return Decimal('0.00')
        except Exception as e:
            logger.error(f"Error calculating original subtotal for order item {self.id}: {str(e)}")
            return Decimal('0.00')

    def calculate_subtotal(self):
        """Calculate subtotal, applying UserExclusivePrice discounts."""
        try:
            item_subtotal = self.calculate_original_subtotal()
            if self.user_exclusive_price:
                discount_percentage = self.user_exclusive_price.discount_percentage
                discount = discount_percentage / Decimal('100.00')
                item_subtotal = item_subtotal * (Decimal('1.00') - discount)
            return item_subtotal.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except Exception as e:
            logger.error(f"Error calculating subtotal for order item {self.id}: {str(e)}")
            return Decimal('0.00')

    def clean(self):
        errors = {}
        try:
            if not self.item:
                errors['item'] = "Please select an item for this order entry."
            elif not self.pricing_tier:
                errors['pricing_tier'] = "Please select a pricing tier for this order entry."
            elif self.pack_quantity <= 0:
                errors['pack_quantity'] = "Pack quantity must be a positive number."
            if self.item and self.pricing_tier:
                if self.pricing_tier.product_variant != self.item.product_variant:
                    errors['pricing_tier'] = "Pricing tier must belong to the same product variant as the item."
                else:
                    units_per_pack = self.item.units_per_pack or 1
                    if self.pack_quantity < self.pricing_tier.range_start:
                        errors['pack_quantity'] = (
                            f"Pack quantity {self.pack_quantity} is below the pricing tier range "
                            f"{self.pricing_tier.range_start}-{'+' if self.pricing_tier.no_end_range else self.pricing_tier.range_end}."
                        )
                    elif not self.pricing_tier.no_end_range and self.pack_quantity > self.pricing_tier.range_end:
                        errors['pack_quantity'] = (
                            f"Pack quantity {self.pack_quantity} exceeds the pricing tier range "
                            f"{self.pricing_tier.range_start}-{self.pricing_tier.range_end}."
                        )
                    pricing_data = PricingTierData.objects.filter(pricing_tier=self.pricing_tier, item=self.item).first()
                    if not pricing_data:
                        errors['pricing_tier'] = "No pricing data found for this item and pricing tier."
            if self.item and self.item.track_inventory:
                total_units = self.total_units
                if self.item.stock is None or total_units > self.item.stock:
                    errors['pack_quantity'] = (
                        f"Insufficient stock for {self.item.sku}. Available: {self.item.stock or 0} units, Required: {total_units} units."
                    )
            if self.user_exclusive_price:
                if self.user_exclusive_price.item != self.item:
                    errors['user_exclusive_price'] = "User exclusive price must correspond to the selected item."
                elif self.user_exclusive_price.user != self.order.user:
                    errors['user_exclusive_price'] = "User exclusive price must correspond to the order's user."
        except Exception as e:
            logger.error(f"Error cleaning order item {self.id}: {str(e)}")
            errors['__all__'] = "An unexpected error occurred while validating the order item."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        try:
            if not self.item:
                raise ValidationError({"item": "OrderItem cannot be saved without an item."})
            with transaction.atomic():
                existing_order_item = OrderItem.objects.filter(
                    order=self.order,
                    item=self.item,
                ).exclude(pk=self.pk).first()
                if existing_order_item:
                    existing_order_item.pack_quantity = self.pack_quantity
                    existing_order_item.pricing_tier = self.pricing_tier
                    existing_order_item.user_exclusive_price = self.user_exclusive_price
                    existing_order_item.unit_type = self.unit_type
                    existing_order_item.full_clean()
                    existing_order_item.save(*args, **kwargs)
                    try:
                        self.order.update_order()
                    except Exception as e:
                        logger.error(f"Error updating order {self.order.id} for existing item: {str(e)}")
                    self.pk = existing_order_item.pk
                    return existing_order_item
                else:
                    self.full_clean()
                    super().save(*args, **kwargs)
                    try:
                        self.order.update_order()
                    except Exception as e:
                        logger.error(f"Error updating order {self.order.id} for new item: {str(e)}")
                    return self
        except ValidationError as e:
            raise
        except Exception as e:
            logger.error(f"Error saving order item {self.id}: {str(e)}")
            raise ValidationError({"__all__": "An unexpected error occurred while saving the order item."})
        # email template


# testing
# deploy
# products upload
