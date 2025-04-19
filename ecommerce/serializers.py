from rest_framework import serializers
from ecommerce.models import Category, Product, ProductImage, ProductVariant, PricingTier, PricingTierData, TableField, Item, ItemImage, ItemData, UserExclusivePrice

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'description', 'image', 'created_at']

class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ['id', 'product', 'image', 'created_at']

class ProductSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = ['id', 'category', 'name', 'description', 'is_new', 'created_at', 'images']

class PricingTierDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = PricingTierData
        fields = ['id', 'item', 'pricing_tier', 'price', 'created_at']

class PricingTierSerializer(serializers.ModelSerializer):
    pricing_data = PricingTierDataSerializer(many=True, read_only=True)

    class Meta:
        model = PricingTier
        fields = ['id', 'product_variant', 'tier_type', 'range_start', 'range_end', 'created_at', 'pricing_data']

class ProductVariantSerializer(serializers.ModelSerializer):
    pricing_tiers = PricingTierSerializer(many=True, read_only=True)

    class Meta:
        model = ProductVariant
        fields = [
            'id', 'product', 'name', 'units_per_pack', 'units_per_pallet',
            'show_units_per', 'created_at', 'pricing_tiers'
        ]

class TableFieldSerializer(serializers.ModelSerializer):
    class Meta:
        model = TableField
        fields = ['id', 'product_variant', 'name', 'field_type', 'created_at']

    def validate_name(self, value):
        if value.lower() in TableField.RESERVED_NAMES:
            raise serializers.ValidationError(f"Field name '{value}' is reserved and cannot be used.")
        return value

class ItemImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemImage
        fields = ['id', 'item', 'image', 'created_at']

class ItemSerializer(serializers.ModelSerializer):
    images = ItemImageSerializer(many=True, read_only=True)
    pricing_tier_data = PricingTierDataSerializer(many=True, read_only=True)

    class Meta:
        model = Item
        fields = [
            'id', 'product_variant', 'sku', 'is_physical_product', 'weight', 'weight_unit',
            'track_inventory', 'stock', 'title', 'status', 'created_at', 'images', 'pricing_tier_data'
        ]

    def validate(self, data):
        is_physical_product = data.get('is_physical_product', False)
        weight = data.get('weight')
        weight_unit = data.get('weight_unit')
        track_inventory = data.get('track_inventory', False)
        stock = data.get('stock')
        title = data.get('title')

        if is_physical_product:
            if weight is None or weight <= 0:
                raise serializers.ValidationError("Weight must be provided and greater than 0 for a physical product.")
            if not weight_unit:
                raise serializers.ValidationError("Weight unit must be provided for a physical product.")
        else:
            data['weight'] = None
            data['weight_unit'] = None

        if track_inventory:
            if stock is None or stock < 0:
                raise serializers.ValidationError("Stock must be provided and non-negative when tracking inventory.")
            if not title:
                raise serializers.ValidationError("Title must be provided when tracking inventory.")
        else:
            data['stock'] = None
            data['title'] = None

        return data

class ItemDataSerializer(serializers.ModelSerializer):
    field_id = serializers.PrimaryKeyRelatedField(
        queryset=TableField.objects.all(), source='field', write_only=True
    )

    class Meta:
        model = ItemData
        fields = ['id', 'item', 'field', 'field_id', 'value_text', 'value_number', 'value_image', 'created_at']
        read_only_fields = ['field', 'created_at']

    def validate(self, data):
        field = data.get('field')
        value_text = data.get('value_text')
        value_number = data.get('value_number')
        value_image = data.get('value_image')

        if value_text == '':
            value_text = None
        if value_number == '':
            value_number = None
        if value_image == '':
            value_image = None

        if field.field_type == 'text':
            if value_text is None:
                raise serializers.ValidationError("A non-empty value_text is required for a text field.")
            if value_number is not None or value_image:
                raise serializers.ValidationError("For a text field, only value_text should be provided.")
        elif field.field_type == 'number':
            if value_number is None:
                raise serializers.ValidationError("A non-empty value_number is required for a number field.")
            if value_text is not None or value_image:
                raise serializers.ValidationError("For a number field, only value_number should be provided.")
        elif field.field_type == 'price':
            if value_number is None or value_number < 0:
                raise serializers.ValidationError("A non-negative value_number is required for a price field.")
            if value_text is not None or value_image:
                raise serializers.ValidationError("For a price field, only value_number should be provided.")
        elif field.field_type == 'image':
            if not value_image:
                raise serializers.ValidationError("A non-empty value_image is required for an image field.")
            if value_text is not None or value_number is not None:
                raise serializers.ValidationError("For an image field, only value_image should be provided.")

        data['value_text'] = value_text
        data['value_number'] = value_number
        data['value_image'] = value_image
        return data

class UserExclusivePriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserExclusivePrice
        fields = ['id', 'user', 'item', 'discount_percentage', 'created_at']