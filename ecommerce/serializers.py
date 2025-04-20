from rest_framework import serializers
from ecommerce.models import Category, Product, ProductImage, ProductVariant, PricingTier, PricingTierData, TableField, Item, ItemImage, ItemData, UserExclusivePrice

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'description', 'image', 'slider_image', 'created_at']

class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ['id', 'product', 'image', 'created_at']

class ProductSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    category = CategorySerializer(read_only=True)

    class Meta:
        model = Product
        fields = ['id', 'category', 'name', 'slug', 'description', 'is_new', 'created_at', 'images']

class PricingTierDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = PricingTierData
        fields = ['id', 'item', 'pricing_tier', 'price', 'created_at']

class PricingTierSerializer(serializers.ModelSerializer):
    pricing_data = PricingTierDataSerializer(many=True, read_only=True)

    class Meta:
        model = PricingTier
        fields = ['id', 'product_variant', 'tier_type', 'range_start', 'range_end', 'no_end_range', 'created_at', 'pricing_data']

    def validate(self, data):
        tier_type = data.get('tier_type')
        no_end_range = data.get('no_end_range')
        range_end = data.get('range_end')
        product_variant = data.get('product_variant')

        if no_end_range and range_end is not None:
            raise serializers.ValidationError("Range end must be null when 'No End Range' is checked.")
        if not no_end_range and range_end is None:
            raise serializers.ValidationError("Range end is required when 'No End Range' is not checked.")

        if product_variant:
            show_units_per = product_variant.show_units_per
            if show_units_per == 'pack' and tier_type != 'pack':
                raise serializers.ValidationError("When show_units_per is 'pack', tier_type must be 'pack'.")
            if show_units_per == 'pallet' and tier_type != 'pallet':
                raise serializers.ValidationError("When show_units_per is 'pallet', tier_type must be 'pallet'.")

        return data

class ProductVariantSerializer(serializers.ModelSerializer):
    pricing_tiers = PricingTierSerializer(many=True, read_only=True)

    class Meta:
        model = ProductVariant
        fields = [
            'id', 'product', 'name', 'units_per_pack', 'units_per_pallet',
            'show_units_per', 'created_at', 'pricing_tiers'
        ]

    def validate(self, data):
        show_units_per = data.get('show_units_per')
        if self.instance:
            pricing_tiers = self.instance.pricing_tiers.all()
            pack_tiers = [tier for tier in pricing_tiers if tier.tier_type == 'pack']
            pallet_tiers = [tier for tier in pricing_tiers if tier.tier_type == 'pallet']

            if show_units_per == 'pack':
                if pallet_tiers:
                    raise serializers.ValidationError("Pallet Pricing Tiers are not allowed when show_units_per is 'pack'.")
                pack_no_end = [tier for tier in pack_tiers if tier.no_end_range]
                if len(pack_no_end) != 1:
                    raise serializers.ValidationError("Exactly one 'pack' Pricing Tier must have 'No End Range' checked.")
            elif show_units_per == 'pallet':
                if pack_tiers:
                    raise serializers.ValidationError("Pack Pricing Tiers are not allowed when show_units_per is 'pallet'.")
                pallet_no_end = [tier for tier in pallet_tiers if tier.no_end_range]
                if len(pallet_no_end) != 1:
                    raise serializers.ValidationError("Exactly one 'pallet' Pricing Tier must have 'No End Range' checked.")
            elif show_units_per == 'both':
                if not pack_tiers or not pallet_tiers:
                    raise serializers.ValidationError("At least one 'pack' and one 'pallet' Pricing Tier are required.")
                pack_no_end = [tier for tier in pack_tiers if tier.no_end_range]
                pallet_no_end = [tier for tier in pallet_tiers if tier.no_end_range]
                if len(pack_no_end) != 1 or len(pallet_no_end) != 1:
                    raise serializers.ValidationError("Exactly one 'pack' and one 'pallet' Pricing Tier must have 'No End Range' checked.")

        return data

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

class ItemDataSerializer(serializers.ModelSerializer):
    field_id = serializers.PrimaryKeyRelatedField(
        queryset=TableField.objects.all(), source='field', write_only=True
    )
    field = TableFieldSerializer(read_only=True)

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

class ItemSerializer(serializers.ModelSerializer):
    images = ItemImageSerializer(many=True, read_only=True)
    pricing_tier_data = PricingTierDataSerializer(many=True, read_only=True)
    data_entries = ItemDataSerializer(many=True, read_only=True)

    class Meta:
        model = Item
        fields = [
            'id', 'product_variant', 'sku', 'is_physical_product', 'weight', 'weight_unit',
            'track_inventory', 'stock', 'title', 'status', 'created_at', 'images',
            'pricing_tier_data', 'data_entries'
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

class UserExclusivePriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserExclusivePrice
        fields = ['id', 'user', 'item', 'discount_percentage', 'created_at']