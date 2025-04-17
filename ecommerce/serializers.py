from rest_framework import serializers
from .models import Category, CategoryImage, Product, SubCategory, TableField, ProductVariant, ProductVariantData, UserExclusivePrice

class CategoryImageSerializer(serializers.ModelSerializer):
    image = serializers.ImageField()

    class Meta:
        model = CategoryImage
        fields = ['id', 'image', 'created_at']
        read_only_fields = ['id', 'created_at']

class CategorySerializer(serializers.ModelSerializer):
    images = CategoryImageSerializer(many=True, read_only=True)
    image = serializers.ImageField()

    class Meta:
        model = Category
        fields = ['id', 'name', 'description', 'image', 'images', 'created_at']
        read_only_fields = ['id', 'created_at']

class ProductSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), source='category', write_only=True
    )

    class Meta:
        model = Product
        fields = ['id', 'category', 'category_id', 'name', 'description', 'is_new', 'created_at']
        read_only_fields = ['id', 'created_at']

class TableFieldSerializer(serializers.ModelSerializer):
    class Meta:
        model = TableField
        fields = ['id', 'subcategory', 'name', 'field_type', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate(self, data):
        # Ensure unique_together constraint for subcategory and name
        subcategory = data.get('subcategory')
        name = data.get('name')
        if TableField.objects.filter(subcategory=subcategory, name=name).exists():
            raise serializers.ValidationError("A TableField with this name already exists for the subcategory.")
        return data

class SubCategorySerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(), source='product', write_only=True
    )
    table_fields = TableFieldSerializer(many=True, read_only=True)

    class Meta:
        model = SubCategory
        fields = ['id', 'product', 'product_id', 'name', 'table_fields', 'created_at']
        read_only_fields = ['id', 'created_at']

class ProductVariantDataSerializer(serializers.ModelSerializer):
    field = TableFieldSerializer(read_only=True)
    field_id = serializers.PrimaryKeyRelatedField(
        queryset=TableField.objects.all(), source='field', write_only=True
    )

    class Meta:
        model = ProductVariantData
        fields = ['id', 'variant', 'field', 'field_id', 'value_text', 'value_number', 'value_image', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate(self, data):
        field = data.get('field')
        value_text = data.get('value_text')
        value_number = data.get('value_number')
        value_image = data.get('value_image')

        # Ensure only the appropriate value field is provided based on field_type
        if field.field_type == 'text':
            if value_number is not None or value_image is not None:
                raise serializers.ValidationError("For a text field, only value_text should be provided.")
        elif field.field_type == 'number':
            if value_text is not None or value_image is not None:
                raise serializers.ValidationError("For a number field, only value_number should be provided.")
        elif field.field_type == 'image':
            if value_text is not None or value_number is not None:
                raise serializers.ValidationError("For an image field, only value_image should be provided.")
        return data

class ProductVariantSerializer(serializers.ModelSerializer):
    subcategory = SubCategorySerializer(read_only=True)
    subcategory_id = serializers.PrimaryKeyRelatedField(
        queryset=SubCategory.objects.all(), source='subcategory', write_only=True
    )
    data_entries = ProductVariantDataSerializer(many=True, read_only=True)

    class Meta:
        model = ProductVariant
        fields = ['id', 'subcategory', 'subcategory_id', 'data_entries', 'created_at']
        read_only_fields = ['id', 'created_at']

class UserExclusivePriceSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source='user', write_only=True
    )
    product = ProductSerializer(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(), source='product', write_only=True
    )

    class Meta:
        model = UserExclusivePrice
        fields = ['id', 'user', 'user_id', 'product', 'product_id', 'exclusive_price', 'created_at']
        read_only_fields = ['id', 'created_at']