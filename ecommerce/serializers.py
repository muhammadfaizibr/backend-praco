from rest_framework import serializers
from ecommerce.models import (
    Category, Product, ProductImage, ProductVariant, PricingTier, PricingTierData,
    TableField, Item, ItemImage, ItemData, UserExclusivePrice, Cart, CartItem, Order, OrderItem
)
from decimal import Decimal, ROUND_HALF_UP
from django.core.exceptions import PermissionDenied

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
        if not product_variant:
            raise serializers.ValidationError("Product variant is required.")

        if product_variant:
            show_units_per = product_variant.show_units_per
            if show_units_per == 'pack' and tier_type != 'pack':
                raise serializers.ValidationError("Tier type must be 'pack' when show_units_per is 'Pack'.")
            if show_units_per == 'both' and tier_type not in ['pack', 'pallet']:
                raise serializers.ValidationError("Tier type must be 'pack' or 'pallet' when show_units_per is 'Both'.")

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
        units_per_pack = data.get('units_per_pack', 6)
        units_per_pallet = data.get('units_per_pallet', 0)

        if show_units_per == 'both' and units_per_pallet <= units_per_pack:
            raise serializers.ValidationError("Units per pallet must be greater than units per pack when show_units_per is 'Both'.")
        if show_units_per == 'pack' and units_per_pallet != 0:
            raise serializers.ValidationError("Units per pallet must be 0 when show_units_per is 'Pack'.")

        if self.instance and self.instance.pk:
            pricing_tiers = self.instance.pricing_tiers.all()
            pack_tiers = [tier for tier in pricing_tiers if tier.tier_type == 'pack']
            pallet_tiers = [tier for tier in pricing_tiers if tier.tier_type == 'pallet']

            if show_units_per == 'pack':
                if not pack_tiers:
                    raise serializers.ValidationError("At least one 'pack' pricing tier is required when show_units_per is 'Pack'.")
                if pallet_tiers:
                    raise serializers.ValidationError("Pallet pricing tiers are not allowed when show_units_per is 'Pack'.")
                pack_no_end = [tier for tier in pack_tiers if tier.no_end_range]
                if len(pack_no_end) != 1:
                    raise serializers.ValidationError("Exactly one 'pack' pricing tier must have 'No End Range' checked.")
            elif show_units_per == 'both':
                if not pack_tiers:
                    raise serializers.ValidationError("At least one 'pack' pricing tier is required when show_units_per is 'Both'.")
                if not pallet_tiers:
                    raise serializers.ValidationError("At least one 'pallet' pricing tier is required when show_units_per is 'Both'.")
                pack_no_end = [tier for tier in pack_tiers if tier.no_end_range]
                pallet_no_end = [tier for tier in pallet_tiers if tier.no_end_range]
                if len(pack_no_end) != 1:
                    raise serializers.ValidationError("Exactly one 'pack' pricing tier must have 'No End Range' checked.")
                if len(pallet_no_end) != 1:
                    raise serializers.ValidationError("Exactly one 'pallet' pricing tier must have 'No End Range' checked.")

        return data

class TableFieldSerializer(serializers.ModelSerializer):
    class Meta:
        model = TableField
        fields = ['id', 'product_variant', 'name', 'field_type', 'long_field', 'created_at']

    def validate_name(self, value):
        if value.lower() in TableField.RESERVED_NAMES:
            raise serializers.ValidationError(f"Field name '{value}' is reserved and cannot be used.")
        return value

    def validate_field_type(self, value):
        if value not in [choice[0] for choice in TableField.FIELD_TYPES]:
            raise serializers.ValidationError(f"Field type must be one of: {', '.join([choice[0] for choice in TableField.FIELD_TYPES])}.")
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
                raise serializers.ValidationError(f"Provide a value for the text field '{field.name}'.")
            if value_number is not None or value_image:
                raise serializers.ValidationError(f"Field '{field.name}' only accepts text values.")
        elif field.field_type == 'number':
            if value_number is None:
                raise serializers.ValidationError(f"Provide a number for the field '{field.name}'.")
            if value_text is not None or value_image:
                raise serializers.ValidationError(f"Field '{field.name}' only accepts number values.")
        elif field.field_type == 'image':
            if not value_image:
                raise serializers.ValidationError(f"Upload an image for the field '{field.name}'.")
            if value_text is not None or value_number is not None:
                raise serializers.ValidationError(f"Field '{field.name}' only accepts image values.")

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
    cart = serializers.PrimaryKeyRelatedField(queryset=Cart.objects.all())
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.all(), required=True)
    pricing_tier = serializers.PrimaryKeyRelatedField(queryset=PricingTier.objects.all())
    user_exclusive_price = serializers.PrimaryKeyRelatedField(
        queryset=UserExclusivePrice.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = CartItem
        fields = ['id', 'cart', 'item', 'pricing_tier', 'pack_quantity', 'unit_type', 'user_exclusive_price', 'created_at']
        read_only_fields = ['created_at', 'unit_type']

    def validate(self, data):
        instance_data = {
            'cart': data.get('cart', getattr(self.instance, 'cart', None)),
            'item': data.get('item', getattr(self.instance, 'item', None)),
            'pricing_tier': data.get('pricing_tier', getattr(self.instance, 'pricing_tier', None)),
            'pack_quantity': data.get('pack_quantity', 1),
            'unit_type': data.get('unit_type', 'pack'),
            'user_exclusive_price': data.get('user_exclusive_price'),
        }
        instance = CartItem(**instance_data)

        if instance.pack_quantity <= 0:
            raise serializers.ValidationError("Pack quantity must be positive.")
        if instance.pricing_tier and instance.item and instance.pricing_tier.product_variant != instance.item.product_variant:
            raise serializers.ValidationError("Pricing tier must belong to the same product variant as the item.")
        if instance.user_exclusive_price:
            if instance.item and instance.user_exclusive_price.item != instance.item:
                raise serializers.ValidationError("User exclusive price must correspond to the selected item.")
            if instance.cart and instance.user_exclusive_price.user != instance.cart.user:
                raise serializers.ValidationError("User exclusive price must correspond to the cart's user.")

        return data

    def get_price_per_unit(self, obj):
        pricing_data = PricingTierData.objects.filter(pricing_tier=obj.pricing_tier, item=obj.item).first()
        return pricing_data.price if pricing_data else Decimal('0.00')

    def get_price_per_pack(self, obj):
        pricing_data = PricingTierData.objects.filter(pricing_tier=obj.pricing_tier, item=obj.item).first()
        if pricing_data and obj.item.product_variant:
            return pricing_data.price * Decimal(obj.item.product_variant.units_per_pack)
        return Decimal('0.00')

    def get_subtotal(self, obj):
        pricing_data = PricingTierData.objects.filter(pricing_tier=obj.pricing_tier, item=obj.item).first()
        if pricing_data and obj.item.product_variant:
            units_per_pack = obj.item.product_variant.units_per_pack
            per_pack_price = pricing_data.price * Decimal(units_per_pack)
            return (per_pack_price * Decimal(obj.pack_quantity)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return Decimal('0.00')

    def get_total(self, obj):
        subtotal = self.get_subtotal(obj)
        discount_percentage = obj.user_exclusive_price.discount_percentage if obj.user_exclusive_price else Decimal('0.00')
        discount = discount_percentage / Decimal('100.00')
        return (subtotal * (Decimal('1.00') - discount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def get_weight(self, obj):
        item_weight_kg = obj.convert_weight_to_kg(obj.item.weight, obj.item.weight_unit)
        total_units = obj.total_units
        return (item_weight_kg * Decimal(total_units)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation.update({
            'price_per_unit': self.get_price_per_unit(instance),
            'price_per_pack': self.get_price_per_pack(instance),
            'subtotal': self.get_subtotal(instance),
            'total': self.get_total(instance),
            'weight': self.get_weight(instance),
        })
        return representation

    def create(self, validated_data):
        cart = validated_data.get('cart')
        item = validated_data.get('item')
        pricing_tier = validated_data.get('pricing_tier')
        pack_quantity = validated_data.get('pack_quantity', 1)
        unit_type = validated_data.get('unit_type', 'pack')
        user_exclusive_price = validated_data.get('user_exclusive_price')

        cart_item = CartItem(
            cart=cart,
            item=item,
            pricing_tier=pricing_tier,
            pack_quantity=pack_quantity,
            unit_type=unit_type,
            user_exclusive_price=user_exclusive_price
        )
        cart_item.full_clean()
        cart_item.save()
        return cart_item

    def update(self, instance, validated_data):
        # Do not allow updating the item field
        instance.pack_quantity = validated_data.get('pack_quantity', instance.pack_quantity)
        instance.pricing_tier = validated_data.get('pricing_tier', instance.pricing_tier)
        instance.user_exclusive_price = validated_data.get('user_exclusive_price', instance.user_exclusive_price)
        instance.full_clean()
        instance.save()
        return instance

class CartItemDetailSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)  # Explicitly define the item field to use ItemSerializer

    class Meta:
        model = CartItem
        fields = ['id', 'cart', 'item', 'pricing_tier', 'pack_quantity', 'unit_type', 'user_exclusive_price', 'created_at']
        # Removed depth=4 since we're explicitly defining nested serializers

    def get_price_per_unit(self, obj):
        pricing_data = PricingTierData.objects.filter(pricing_tier=obj.pricing_tier, item=obj.item).first()
        return pricing_data.price if pricing_data else Decimal('0.00')

    def get_price_per_pack(self, obj):
        pricing_data = PricingTierData.objects.filter(pricing_tier=obj.pricing_tier, item=obj.item).first()
        if pricing_data and obj.item.product_variant:
            return pricing_data.price * Decimal(obj.item.product_variant.units_per_pack)
        return Decimal('0.00')

    def get_subtotal(self, obj):
        pricing_data = PricingTierData.objects.filter(pricing_tier=obj.pricing_tier, item=obj.item).first()
        if pricing_data and obj.item.product_variant:
            units_per_pack = obj.item.product_variant.units_per_pack
            per_pack_price = pricing_data.price * Decimal(units_per_pack)
            return (per_pack_price * Decimal(obj.pack_quantity)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return Decimal('0.00')

    def get_total(self, obj):
        subtotal = self.get_subtotal(obj)
        discount_percentage = obj.user_exclusive_price.discount_percentage if obj.user_exclusive_price else Decimal('0.00')
        discount = discount_percentage / Decimal('100.00')
        return (subtotal * (Decimal('1.00') - discount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def get_weight(self, obj):
        item_weight_kg = obj.convert_weight_to_kg(obj.item.weight, obj.item.weight_unit)
        total_units = obj.total_units
        return (item_weight_kg * Decimal(total_units)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation.update({
            'price_per_unit': self.get_price_per_unit(instance),
            'price_per_pack': self.get_price_per_pack(instance),
            'subtotal': self.get_subtotal(instance),
            'total': self.get_total(instance),
            'weight': self.get_weight(instance),
        })
        return representation

class CartSerializer(serializers.ModelSerializer):
    items = CartItemDetailSerializer(many=True, read_only=True)

    class Meta:
        model = Cart
        fields = ['id', 'user', 'items', 'vat', 'discount', 'created_at', 'updated_at']
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']

    def get_subtotal(self, obj):
        return obj.calculate_subtotal()

    def get_total(self, obj):
        return obj.calculate_total()

    def get_total_weight(self, obj):
        return obj.calculate_total_weight()

    def get_total_units(self, obj):
        return obj.calculate_total_units_and_packs()[0]

    def get_total_packs(self, obj):
        return obj.calculate_total_units_and_packs()[1]

    def to_representation(self, instance):
        if not isinstance(instance, Cart):
            print(f"Unexpected instance type in CartSerializer: {type(instance)}, value: {instance}")
            return {
                'id': None,
                'user': None,
                'items': [],
                'vat': str(Decimal('0.00')),
                'discount': str(Decimal('0.00')),
                'created_at': None,
                'updated_at': None,
                'subtotal': str(Decimal('0.00')),
                'total': str(Decimal('0.00')),
                'total_weight': str(Decimal('0.00')),
                'total_units': 0,
                'total_packs': 0,
            }

        representation = super().to_representation(instance)
        representation.update({
            'subtotal': str(self.get_subtotal(instance)),
            'total': str(self.get_total(instance)),
            'total_weight': str(self.get_total_weight(instance)),
            'total_units': self.get_total_units(instance),
            'total_packs': self.get_total_packs(instance),
        })
        return representation

class OrderItemSerializer(serializers.ModelSerializer):
    order = serializers.PrimaryKeyRelatedField(queryset=Order.objects.all())
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.all(), required=True)
    pricing_tier = serializers.PrimaryKeyRelatedField(queryset=PricingTier.objects.all())
    user_exclusive_price = serializers.PrimaryKeyRelatedField(
        queryset=UserExclusivePrice.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = OrderItem
        fields = ['id', 'order', 'item', 'pricing_tier', 'pack_quantity', 'unit_type', 'user_exclusive_price', 'created_at']
        read_only_fields = ['created_at', 'unit_type']

    def validate(self, data):
        instance_data = {
            'order': data.get('order', getattr(self.instance, 'order', None)),
            'item': data.get('item', getattr(self.instance, 'item', None)),
            'pricing_tier': data.get('pricing_tier', getattr(self.instance, 'pricing_tier', None)),
            'pack_quantity': data.get('pack_quantity', 1),
            'unit_type': data.get('unit_type', 'pack'),
            'user_exclusive_price': data.get('user_exclusive_price'),
        }
        instance = OrderItem(**instance_data)

        if instance.pack_quantity <= 0:
            raise serializers.ValidationError("Pack quantity must be positive.")
        if instance.pricing_tier and instance.item and instance.pricing_tier.product_variant != instance.item.product_variant:
            raise serializers.ValidationError("Pricing tier must belong to the same product variant as the item.")
        if instance.user_exclusive_price:
            if instance.item and instance.user_exclusive_price.item != instance.item:
                raise serializers.ValidationError("User exclusive price must correspond to the selected item.")
            if instance.order and instance.user_exclusive_price.user != instance.order.user:
                raise serializers.ValidationError("User exclusive price must correspond to the order's user.")

        return data

    def get_price_per_unit(self, obj):
        pricing_data = PricingTierData.objects.filter(pricing_tier=obj.pricing_tier, item=obj.item).first()
        return pricing_data.price if pricing_data else Decimal('0.00')

    def get_price_per_pack(self, obj):
        pricing_data = PricingTierData.objects.filter(pricing_tier=obj.pricing_tier, item=obj.item).first()
        if pricing_data and obj.item.product_variant:
            return pricing_data.price * Decimal(obj.item.product_variant.units_per_pack)
        return Decimal('0.00')

    def get_subtotal(self, obj):
        pricing_data = PricingTierData.objects.filter(pricing_tier=obj.pricing_tier, item=obj.item).first()
        if pricing_data and obj.item.product_variant:
            units_per_pack = obj.item.product_variant.units_per_pack
            per_pack_price = pricing_data.price * Decimal(units_per_pack)
            return (per_pack_price * Decimal(obj.pack_quantity)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return Decimal('0.00')

    def get_total(self, obj):
        subtotal = self.get_subtotal(obj)
        discount_percentage = obj.user_exclusive_price.discount_percentage if obj.user_exclusive_price else Decimal('0.00')
        discount = discount_percentage / Decimal('100.00')
        return (subtotal * (Decimal('1.00') - discount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def get_weight(self, obj):
        item_weight_kg = obj.convert_weight_to_kg(obj.item.weight, obj.item.weight_unit)
        total_units = obj.total_units
        return (item_weight_kg * Decimal(total_units)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation.update({
            'price_per_unit': self.get_price_per_unit(instance),
            'price_per_pack': self.get_price_per_pack(instance),
            'subtotal': self.get_subtotal(instance),
            'total': self.get_total(instance),
            'weight': self.get_weight(instance),
        })
        return representation

    def create(self, validated_data):
        order = validated_data.get('order')
        item = validated_data.get('item')
        pricing_tier = validated_data.get('pricing_tier')
        pack_quantity = validated_data.get('pack_quantity', 1)
        unit_type = validated_data.get('unit_type', 'pack')
        user_exclusive_price = validated_data.get('user_exclusive_price')

        order_item = OrderItem(
            order=order,
            item=item,
            pricing_tier=pricing_tier,
            pack_quantity=pack_quantity,
            unit_type=unit_type,
            user_exclusive_price=user_exclusive_price
        )
        order_item.full_clean()
        order_item.save()
        return order_item

    def update(self, instance, validated_data):
        instance.pack_quantity = validated_data.get('pack_quantity', instance.pack_quantity)
        instance.pricing_tier = validated_data.get('pricing_tier', instance.pricing_tier)
        instance.user_exclusive_price = validated_data.get('user_exclusive_price', instance.user_exclusive_price)
        instance.full_clean()
        instance.save()
        return instance

class OrderItemDetailSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)

    class Meta:
        model = OrderItem
        fields = ['id', 'order', 'item', 'pricing_tier', 'pack_quantity', 'unit_type', 'user_exclusive_price', 'created_at']

    def get_price_per_unit(self, obj):
        pricing_data = PricingTierData.objects.filter(pricing_tier=obj.pricing_tier, item=obj.item).first()
        return pricing_data.price if pricing_data else Decimal('0.00')

    def get_price_per_pack(self, obj):
        pricing_data = PricingTierData.objects.filter(pricing_tier=obj.pricing_tier, item=obj.item).first()
        if pricing_data and obj.item.product_variant:
            return pricing_data.price * Decimal(obj.item.product_variant.units_per_pack)
        return Decimal('0.00')

    def get_subtotal(self, obj):
        pricing_data = PricingTierData.objects.filter(pricing_tier=obj.pricing_tier, item=obj.item).first()
        if pricing_data and obj.item.product_variant:
            units_per_pack = obj.item.product_variant.units_per_pack
            per_pack_price = pricing_data.price * Decimal(units_per_pack)
            return (per_pack_price * Decimal(obj.pack_quantity)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return Decimal('0.00')

    def get_total(self, obj):
        subtotal = self.get_subtotal(obj)
        discount_percentage = obj.user_exclusive_price.discount_percentage if obj.user_exclusive_price else Decimal('0.00')
        discount = discount_percentage / Decimal('100.00')
        return (subtotal * (Decimal('1.00') - discount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def get_weight(self, obj):
        item_weight_kg = obj.convert_weight_to_kg(obj.item.weight, obj.item.weight_unit)
        total_units = obj.total_units
        return (item_weight_kg * Decimal(total_units)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation.update({
            'price_per_unit': self.get_price_per_unit(instance),
            'price_per_pack': self.get_price_per_pack(instance),
            'subtotal': self.get_subtotal(instance),
            'total': self.get_total(instance),
            'weight': self.get_weight(instance),
        })
        return representation

class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemDetailSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = ['id', 'user', 'country', 'address', 'city', 'postal_code', 'items', 'vat', 'discount', 'created_at', 'updated_at']
        read_only_fields = ['id', 'user', 'country', 'created_at', 'updated_at']

    def validate(self, data):
        if not data.get('address'):
            raise serializers.ValidationError({"address": "Address is required."})
        if not data.get('city'):
            raise serializers.ValidationError({"city": "City is required."})
        if not data.get('postal_code'):
            raise serializers.ValidationError({"postal_code": "Postal code is required."})
        return data

    def create(self, validated_data):
        """Set the user from the request context if not provided."""
        user = self.context['request'].user
        if not user.is_authenticated:
            raise PermissionDenied("Authentication required to create an order.")
        validated_data['user'] = user
        return super().create(validated_data)

    def get_subtotal(self, obj):
        return obj.calculate_subtotal()

    def get_total(self, obj):
        return obj.calculate_total()

    def get_total_weight(self, obj):
        return obj.calculate_total_weight()

    def get_total_units(self, obj):
        return obj.calculate_total_units_and_packs()[0]

    def get_total_packs(self, obj):
        return obj.calculate_total_units_and_packs()[1]

    def to_representation(self, instance):
        if not isinstance(instance, Order):
            return {
                'id': None,
                'user': None,
                'country': 'United Kingdom',
                'address': None,
                'city': None,
                'postal_code': None,
                'items': [],
                'vat': str(Decimal('0.00')),
                'discount': str(Decimal('0.00')),
                'created_at': None,
                'updated_at': None,
                'subtotal': str(Decimal('0.00')),
                'total': str(Decimal('0.00')),
                'total_weight': str(Decimal('0.00')),
                'total_units': 0,
                'total_packs': 0,
            }

        representation = super().to_representation(instance)
        representation.update({
            'subtotal': str(self.get_subtotal(instance)),
            'total': str(self.get_total(instance)),
            'total_weight': str(self.get_total_weight(instance)),
            'total_units': self.get_total_units(instance),
            'total_packs': self.get_total_packs(instance),
        })
        return representation

