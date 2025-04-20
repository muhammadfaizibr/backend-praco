from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from ckeditor.fields import RichTextField
from decimal import Decimal

class Category(models.Model):
    name = models.CharField(max_length=255, unique=True)
    description = RichTextField(blank=True)
    image = models.ImageField(upload_to='category_images/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['created_at']),
        ]
        verbose_name = 'category'
        verbose_name_plural = 'categories'

    def clean(self):
        if not self.name:
            raise ValidationError("Category name cannot be empty.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Product(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=255)
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
            raise ValidationError("Product name cannot be empty.")
        if not self.description:
            raise ValidationError("Product description cannot be empty.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.category.name} - {self.name}"

class ProductImage(models.Model):
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
            raise ValidationError("Product image cannot be empty.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Image for {self.product.name}"

class ProductVariant(models.Model):
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
            raise ValidationError("Product variant name cannot be empty.")
        if self.units_per_pack <= 0:
            raise ValidationError("Units per pack must be greater than 0.")
        if self.units_per_pallet <= 0:
            raise ValidationError("Units per pallet must be greater than 0.")

    def validate_pricing_tiers(self):
        pricing_tiers = self.pricing_tiers.all() if self.pk else []
        if not pricing_tiers:
            raise ValidationError("At least one Pricing Tier is required for a Product Variant.")

        pack_tiers = [tier for tier in pricing_tiers if tier.tier_type == 'pack']
        pallet_tiers = [tier for tier in pricing_tiers if tier.tier_type == 'pallet']

        if self.show_units_per == 'pack':
            if not pack_tiers:
                raise ValidationError("At least one 'pack' Pricing Tier is required when show_units_per is 'pack'.")
            if pallet_tiers:
                raise ValidationError("Pallet Pricing Tiers are not allowed when show_units_per is 'pack'.")
            pack_no_end = [tier for tier in pack_tiers if tier.no_end_range]
            if len(pack_no_end) != 1:
                raise ValidationError("Exactly one 'pack' Pricing Tier must have 'No End Range' checked when show_units_per is 'pack'.")
            for tier in pack_tiers:
                if not tier.no_end_range and tier.range_end is None:
                    raise ValidationError("Non-'No End Range' pack tiers must have a defined range_end.")
        elif self.show_units_per == 'pallet':
            if not pallet_tiers:
                raise ValidationError("At least one 'pallet' Pricing Tier is required when show_units_per is 'pallet'.")
            if pack_tiers:
                raise ValidationError("Pack Pricing Tiers are not allowed when show_units_per is 'pallet'.")
            pallet_no_end = [tier for tier in pallet_tiers if tier.no_end_range]
            if len(pallet_no_end) != 1:
                raise ValidationError("Exactly one 'pallet' Pricing Tier must have 'No End Range' checked when show_units_per is 'pallet'.")
            for tier in pallet_tiers:
                if not tier.no_end_range and tier.range_end is None:
                    raise ValidationError("Non-'No End Range' pallet tiers must have a defined range_end.")
        elif self.show_units_per == 'both':
            if not pack_tiers or not pallet_tiers:
                raise ValidationError("At least one 'pack' and one 'pallet' Pricing Tier are required when show_units_per is 'both'.")
            pack_no_end = [tier for tier in pack_tiers if tier.no_end_range]
            pallet_no_end = [tier for tier in pallet_tiers if tier.no_end_range]
            if len(pack_no_end) != 1 or len(pallet_no_end) != 1:
                raise ValidationError("Exactly one 'pack' and one 'pallet' Pricing Tier must have 'No End Range' checked when show_units_per is 'both'.")
            for tier in pack_tiers + pallet_tiers:
                if not tier.no_end_range and tier.range_end is None:
                    raise ValidationError("Non-'No End Range' tiers must have a defined range_end.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.name} - {self.name}"

class PricingTier(models.Model):
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
        if self.range_start is None:
            raise ValidationError("Range start cannot be None.")
        if self.range_start <= 0:
            raise ValidationError("Range start must be greater than 0.")
        if self.no_end_range:
            if self.range_end is not None:
                raise ValidationError("Range end must be blank when 'No End Range' is checked.")
        else:
            if self.range_end is None:
                raise ValidationError("Range end is required when 'No End Range' is not checked.")
            if self.range_end < self.range_start:
                raise ValidationError("Range end must be greater than or equal to range start.")

        if not self.product_variant or not self.product_variant.pk:
            return

        existing_tiers = PricingTier.objects.filter(
            product_variant=self.product_variant,
            tier_type=self.tier_type
        ).exclude(id=self.id)

        for tier in existing_tiers:
            current_end = float('inf') if self.no_end_range else (self.range_end or float('inf'))
            tier_end = float('inf') if tier.no_end_range else (tier.range_end or float('inf'))
            if tier.range_start is None:
                raise ValidationError("Invalid range data in existing tier.")
            if self.range_start <= tier_end and current_end >= tier.range_start:
                raise ValidationError(
                    f"Range {self.range_start}-{self.range_end or '+'} overlaps with existing range "
                    f"{tier.range_start}-{tier.range_end or '+'} for {self.tier_type}."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        range_str = f"{self.range_start}-" + ("+" if self.no_end_range else str(self.range_end))
        return f"{self.product_variant} - {self.tier_type} - {range_str}"

class PricingTierData(models.Model):
    item = models.ForeignKey('Item', on_delete=models.CASCADE, related_name='pricing_tier_data')
    pricing_tier = models.ForeignKey(PricingTier, on_delete=models.CASCADE, related_name='pricing_data')
    price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Price per pack if tier_type is 'pack', per pallet if 'pallet'")
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
        if self.price <= 0:
            raise ValidationError("Price must be greater than 0.")
        if self.pricing_tier.product_variant != self.item.product_variant:
            raise ValidationError("Pricing tier must belong to the same product variant as the item.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.item} - {self.pricing_tier} - Price: {self.price}"

class TableField(models.Model):
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
        print("self.name.lower()", self.name.lower())
        if self.name.lower() in self.RESERVED_NAMES:
            if self.id is None:
                existing_field = TableField.objects.filter(product_variant=self.product_variant, name=self.name).exists()
                if existing_field:
                    raise ValidationError(f"Field name '{self.name}' is reserved and cannot be used.")
            else:
                original = TableField.objects.get(id=self.id)
                if original.name != self.name:
                    raise ValidationError(f"Field name '{self.name}' is reserved and cannot be used.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product_variant.name} - {self.name} ({self.field_type})"

class Item(models.Model):
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

    product_variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name='items')
    sku = models.CharField(max_length=100, unique=True)
    is_physical_product = models.BooleanField(default=False)
    weight = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    weight_unit = models.CharField(max_length=2, choices=WEIGHT_UNIT_CHOICES, blank=True, null=True)
    track_inventory = models.BooleanField(default=False)
    stock = models.IntegerField(blank=True, null=True)
    title = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    created_at = models.DateTimeField(auto_now_add=True)

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
            raise ValidationError("SKU cannot be empty.")
        if self.is_physical_product:
            if self.weight is None or self.weight <= 0:
                raise ValidationError("Weight must be provided and greater than 0 for a physical product.")
            if not self.weight_unit:
                raise ValidationError("Weight unit must be provided for a physical product.")
        else:
            self.weight = None
            self.weight_unit = None
        if self.track_inventory:
            if self.stock is None or self.stock < 0:
                raise ValidationError("Stock must be provided and non-negative when tracking inventory.")
            if not self.title:
                raise ValidationError("Title must be provided when tracking inventory.")
        else:
            self.stock = None
            self.title = None

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Item {self.sku} for {self.product_variant.name} ({self.status})"

class ItemImage(models.Model):
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
            raise ValidationError("Item image cannot be empty.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Image for {self.item}"

class ItemData(models.Model):
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
        if self.value_text == '':
            self.value_text = None
        if self.value_number == '':
            self.value_number = None
        if self.value_image == '':
            self.value_image = None

        if self.field.field_type == 'text':
            if self.value_text is None:
                raise ValidationError("A non-empty value_text is required for a text field.")
            if self.value_number is not None or self.value_image:
                raise ValidationError("For a text field, only value_text should be provided.")
        elif self.field.field_type == 'number':
            if self.value_number is None:
                raise ValidationError("A non-empty value_number is required for a number field.")
            if self.value_text is not None or self.value_image:
                raise ValidationError("For a number field, only value_number should be provided.")
        elif self.field.field_type == 'price':
            if self.value_number is None or self.value_number < 0:
                raise ValidationError("A non-negative value_number is required for a price field.")
            if self.value_text is not None or self.value_image:
                raise ValidationError("For a price field, only value_number should be provided.")
        elif self.field.field_type == 'image':
            if not self.value_image:
                raise ValidationError("A non-empty value_image is required for an image field.")
            if self.value_text is not None or self.value_number is not None:
                raise ValidationError("For an image field, only value_image should be provided.")

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
        if self.discount_percentage < 0 or self.discount_percentage > 100:
            raise ValidationError("Discount percentage must be between 0 and 100.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.email} - {self.item} ({self.discount_percentage}% off)"