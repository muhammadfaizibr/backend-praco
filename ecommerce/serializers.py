from rest_framework import serializers
from ecommerce.models import (
    Category, Product, ProductImage, ProductVariant, PricingTier, PricingTierData,
    TableField, Item, ItemImage, ItemData, UserExclusivePrice, Cart, CartItem, Order, OrderItem
)
from decimal import Decimal

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
    description = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ['id', 'category', 'name', 'slug', 'description', 'is_new', 'created_at', 'images']

    def get_description(self, obj):
        search_headline = self.context.get('search_headline', {}).get(obj.id)
        return search_headline or obj.description

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
    product = ProductSerializer(read_only=True)

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
        fields = ['id', 'product_variant', 'name', 'field_type', 'long_field', 'created_at']

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
    product_variant = ProductVariantSerializer(read_only=True)

    class Meta:
        model = Item
        fields = [
            'id', 'product_variant', 'sku', 'is_physical_product', 'weight', 'weight_unit',
            'track_inventory', 'stock', 'title', 'status', 'created_at', 'images',
            'pricing_tier_data', 'data_entries', 'height', 'width', 'length', 'measurement_unit'
        ]

    def validate(self, data):
        is_physical_product = data.get('is_physical_product', False)
        weight = data.get('weight')
        weight_unit = data.get('weight_unit')
        track_inventory = data.get('track_inventory', False)
        stock = data.get('stock')
        title = data.get('title')
        height = data.get('height')
        width = data.get('width')
        length = data.get('length')
        measurement_unit = data.get('measurement_unit')

        product_variant = data.get('product_variant')
        if not product_variant and self.instance:
            product_variant = self.instance.product_variant

        required_categories = ['box', 'boxes', 'postal', 'postals', 'bag', 'bags']
        category_name = ''
        if product_variant and product_variant.product and product_variant.product.category:
            category_name = product_variant.product.category.name.lower()

        if category_name in required_categories:
            if height is None or height <= 0:
                raise serializers.ValidationError("Height must be provided and greater than 0 for items in categories: box, boxes, postal, postals, bag, bags.")
            if width is None or width <= 0:
                raise serializers.ValidationError("Width must be provided and greater than 0 for items in categories: box, boxes, postal, postals, bag, bags.")
            if length is None or length <= 0:
                raise serializers.ValidationError("Length must be provided and greater than 0 for items in categories: box, boxes, postal, postals, bag, bags.")
            if not measurement_unit:
                raise serializers.ValidationError("Measurement unit must be provided for items in categories: box, boxes, postal, postals, bag, bags.")
            if measurement_unit not in ['MM', 'CM', 'IN', 'M']:
                raise serializers.ValidationError("Measurement unit must be one of: MM, CM, IN, M.")
        else:
            data['height'] = None
            data['width'] = None
            data['length'] = None
            data['measurement_unit'] = None

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

class CartItemSerializer(serializers.ModelSerializer):
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.all())
    pricing_tier = serializers.PrimaryKeyRelatedField(queryset=PricingTier.objects.all())
    user_exclusive_price = serializers.PrimaryKeyRelatedField(
        queryset=UserExclusivePrice.objects.all(),
        allow_null=True
    )

    class Meta:
        model = CartItem
        fields = [
            'id', 'cart', 'item', 'pricing_tier', 'quantity', 'unit_type',
            'unit_price', 'user_exclusive_price', 'created_at'
        ]

    def validate(self, data):
        cart = data.get('cart')
        item = data.get('item')
        pricing_tier = data.get('pricing_tier')
        unit_type = data.get('unit_type')
        quantity = data.get('quantity')
        user_exclusive_price = data.get('user_exclusive_price')

        if pricing_tier.product_variant != item.product_variant:
            raise serializers.ValidationError("Pricing tier must belong to the same product variant as the item.")
        if unit_type != pricing_tier.tier_type:
            raise serializers.ValidationError("Unit type must match the pricing tier type.")
        if item.product_variant.show_units_per == 'pack' and unit_type != 'pack':
            raise serializers.ValidationError("This item only supports 'pack' unit type.")
        if item.product_variant.show_units_per == 'pallet' and unit_type != 'pallet':
            raise serializers.ValidationError("This item only supports 'pallet' unit type.")
        if quantity < pricing_tier.range_start:
            raise serializers.ValidationError(
                f"Quantity {quantity} is below the pricing tier range {pricing_tier.range_start}-"
                f"{'+' if pricing_tier.no_end_range else pricing_tier.range_end}."
            )
        if not pricing_tier.no_end_range and quantity > pricing_tier.range_end:
            raise serializers.ValidationError(
                f"Quantity {quantity} exceeds the pricing tier range {pricing_tier.range_start}-{pricing_tier.range_end}."
            )
        if item.track_inventory:
            units_per = (
                item.product_variant.units_per_pack if unit_type == 'pack'
                else item.product_variant.units_per_pallet
            )
            total_units = quantity * units_per
            if item.stock is None or total_units > item.stock:
                raise serializers.ValidationError(
                    f"Insufficient stock for {item.sku}. Available: {item.stock or 0}, Required: {total_units} units."
                )
        if user_exclusive_price:
            if user_exclusive_price.item != item:
                raise serializers.ValidationError("User exclusive price must apply to the same item.")
            if user_exclusive_price.user != cart.user:
                raise serializers.ValidationError("User exclusive price must belong to the same user as the cart.")
        return data

class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total = serializers.SerializerMethodField()
    user = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Cart
        fields = ['id', 'user', 'items', 'total', 'created_at', 'updated_at']
        read_only_fields = ['user']

    def get_total(self, obj):
        return obj.calculate_total()
    

class OrderItemSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)
    item_id = serializers.PrimaryKeyRelatedField(
        queryset=Item.objects.all(), source='item', write_only=True
    )
    pricing_tier = PricingTierSerializer(read_only=True)
    pricing_tier_id = serializers.PrimaryKeyRelatedField(
        queryset=PricingTier.objects.all(), source='pricing_tier', write_only=True
    )
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = [
            'id', 'order', 'item', 'item_id', 'pricing_tier', 'pricing_tier_id',
            'quantity', 'unit_type', 'unit_price', 'discount_percentage', 'subtotal', 'created_at'
        ]
        read_only_fields = ['unit_price', 'discount_percentage', 'subtotal', 'created_at']

    def validate(self, data):
        quantity = data.get('quantity')
        unit_type = data.get('unit_type')
        item = data.get('item')
        pricing_tier = data.get('pricing_tier')

        if quantity <= 0:
            raise serializers.ValidationError("Quantity must be greater than 0.")
        if unit_type not in ['pack', 'pallet']:
            raise serializers.ValidationError("Unit type must be one of: pack, pallet.")

        if item and pricing_tier:
            if pricing_tier.product_variant != item.product_variant:
                raise serializers.ValidationError("Pricing tier must belong to the same product variant as the item.")
            if pricing_tier.tier_type != unit_type:
                raise serializers.ValidationError("Unit type must match the pricing tier type (pack or pallet).")
            # Validate quantity against pricing tier range
            if quantity < pricing_tier.range_start:
                raise serializers.ValidationError(
                    f"Quantity {quantity} is below the pricing tier range {pricing_tier.range_start}-{'+' if pricing_tier.no_end_range else pricing_tier.range_end}."
                )
            if not pricing_tier.no_end_range and quantity > pricing_tier.range_end:
                raise serializers.ValidationError(
                    f"Quantity {quantity} exceeds the pricing tier range {pricing_tier.range_start}-{pricing_tier.range_end}."
                )
            # Validate stock for pallet quantities
            if item.track_inventory and unit_type == 'pallet':
                total_units = quantity * item.product_variant.units_per_pallet
                if item.stock is None or total_units > item.stock:
                    raise serializers.ValidationError(
                        f"Insufficient stock for {item.sku}. Available: {item.stock or 0}, Required: {total_units} units."
                    )
            # Validate PricingTierData exists
            pricing_data = PricingTierData.objects.filter(item=item, pricing_tier=pricing_tier).first()
            if not pricing_data:
                raise serializers.ValidationError(
                    f"No pricing data found for item {item.sku} with pricing tier {pricing_tier.tier_type} "
                    f"({pricing_tier.range_start}-{'+' if pricing_tier.no_end_range else pricing_tier.range_end})."
                )

        return data

    def create(self, validated_data):
        item = validated_data['item']
        pricing_tier = validated_data['pricing_tier']
        pricing_data = PricingTierData.objects.filter(item=item, pricing_tier=pricing_tier).first()
        if not pricing_data:
            raise serializers.ValidationError(
                f"No pricing data found for item {item.sku} with pricing tier {pricing_tier.tier_type} "
                f"({pricing_tier.range_start}-{'+' if pricing_tier.no_end_range else pricing_tier.range_end})."
            )
        validated_data['unit_price'] = pricing_data.price
        user = self.context['request'].user
        exclusive_price = UserExclusivePrice.objects.filter(user=user, item=item).first()
        validated_data['discount_percentage'] = exclusive_price.discount_percentage if exclusive_price else 0
        return super().create(validated_data)

    def get_subtotal(self, obj):
        return float(obj.subtotal())

class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    user = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'user', 'status', 'total_amount', 'shipping_address',
            'payment_status', 'payment_method', 'transaction_id', 'items',
        ]
        read_only_fields = ['user']

    def validate(self, data):
        total_amount = data.get('total_amount')
        payment_status = data.get('payment_status')
        payment_method = data.get('payment_method')
        transaction_id = data.get('transaction_id')

        if total_amount is not None and total_amount < 0:
            raise serializers.ValidationError("Total amount cannot be negative.")
        if payment_status == 'completed':
            if not payment_method:
                raise serializers.ValidationError("Payment method is required when payment status is 'completed'.")
            if not transaction_id:
                raise serializers.ValidationError("Transaction ID is required when payment status is 'completed'.")

        return data