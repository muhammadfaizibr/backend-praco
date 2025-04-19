from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from ckeditor.fields import RichTextField
from decimal import Decimal

class Category(models.Model):
    name = models.CharField(max_length=255)
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

    def __str__(self):
        return f"Image for {self.product.name}"

class ProductVariant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='product_variants')
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['product', 'name']),
            models.Index(fields=['created_at']),
        ]
        verbose_name = 'product variant'
        verbose_name_plural = 'product variants'

    def __str__(self):
        return f"{self.product.name} - {self.name}"

class TableField(models.Model):
    FIELD_TYPES = (
        ('text', 'Text'),
        ('number', 'Number'),
        ('image', 'Image'),
        ('price', 'Price'),
    )
    product_variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name='table_fields')
    name = models.CharField(max_length=255)
    field_type = models.CharField(max_length=20, choices=FIELD_TYPES, db_index=True)  # Added db_index
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('product_variant', 'name')
        indexes = [
            models.Index(fields=['product_variant', 'name']),
            models.Index(fields=['field_type']),
        ]
        verbose_name = 'table field'
        verbose_name_plural = 'table fields'

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