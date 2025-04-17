from django.db import models
from django.conf import settings

class Category(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='category_images/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['name']),  # For faster lookups on name
            models.Index(fields=['created_at']),  # For sorting and filtering
        ]

    def __str__(self):
        return self.name

class CategoryImage(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='category_images/multiple/')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['category']),  # For faster lookups by category
        ]

    def __str__(self):
        return f"Image for {self.category.name}"

class Product(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=255)
    description = models.TextField()
    is_new = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['category', 'name']),  # For faster lookups by category and name
            models.Index(fields=['created_at']),  # For sorting and filtering
        ]

    def __str__(self):
        return f"{self.category.name} - {self.name}"

class SubCategory(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='subcategories')
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['product', 'name']),  # For faster lookups by product and name
            models.Index(fields=['created_at']),  # For sorting and filtering
        ]

    def __str__(self):
        return f"{self.product.name} - {self.name}"

class TableField(models.Model):
    FIELD_TYPES = (
        ('text', 'Text'),
        ('number', 'Number'),
        ('image', 'Image'),
    )
    subcategory = models.ForeignKey(SubCategory, on_delete=models.CASCADE, related_name='table_fields')
    name = models.CharField(max_length=255)
    field_type = models.CharField(max_length=20, choices=FIELD_TYPES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('subcategory', 'name')
        indexes = [
            models.Index(fields=['subcategory', 'name']),
            models.Index(fields=['field_type']),  # For filtering by field type
        ]

    def __str__(self):
        return f"{self.subcategory.name} - {self.name} ({self.field_type})"

class ProductVariant(models.Model):
    subcategory = models.ForeignKey(SubCategory, on_delete=models.CASCADE, related_name='variants')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['subcategory']),  # For faster lookups by subcategory
            models.Index(fields=['created_at']),  # For sorting and filtering
        ]

    def __str__(self):
        return f"Variant for {self.subcategory.name}"

class ProductVariantData(models.Model):
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name='data_entries')
    field = models.ForeignKey(TableField, on_delete=models.CASCADE, related_name='data_values')
    value_text = models.TextField(blank=True, null=True)
    value_number = models.IntegerField(blank=True, null=True)
    value_image = models.ImageField(upload_to='variant_images/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('variant', 'field')
        indexes = [
            models.Index(fields=['variant', 'field']),
            models.Index(fields=['created_at']),  # For sorting and filtering
        ]

    def __str__(self):
        if self.field.field_type == 'image' and self.value_image:
            return f"{self.variant} - {self.field.name}: {self.value_image.url}"
        return f"{self.variant} - {self.field.name}: {self.value_text or self.value_number or '-'}"

class UserExclusivePrice(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    exclusive_price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'product')
        indexes = [
            models.Index(fields=['user', 'product']),
            models.Index(fields=['created_at']),  # For sorting and filtering
        ]

    def __str__(self):
        return f"Exclusive price for {self.user.username} - {self.product.name}"