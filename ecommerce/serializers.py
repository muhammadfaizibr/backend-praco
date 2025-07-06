from rest_framework import serializers
from ecommerce.models import (
    Category, Product, ProductImage, ProductVariant, PricingTier, PricingTierData,
    TableField, Item, ItemImage, ItemData, UserExclusivePrice, Cart, CartItem, Order, OrderItem, ShippingAddress, BillingAddress
)
from decimal import Decimal, ROUND_HALF_UP
from django.core.exceptions import PermissionDenied
from django.db import transaction
import logging

logger = logging.getLogger(__name__)


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
        range_start = data.get('range_start')
        range_end = data.get('range_end')
        no_end_range = data.get('no_end_range')
        product_variant = data.get('product_variant')

        # Basic validations
        if no_end_range and range_end is not None:
            raise serializers.ValidationError("Range end must be null when 'No End Range' is checked.")
        if not no_end_range and range_end is None:
            raise serializers.ValidationError("Range end is required when 'No End Range' is not checked.")
        if not product_variant:
            raise serializers.ValidationError("Product variant is required.")
        if range_start <= 0:
            raise serializers.ValidationError("Range start must be a positive number.")
        if not no_end_range and range_end <= range_start:
            raise serializers.ValidationError("Range end must be greater than range start.")

        # Validate tier_type against show_units_per
        if product_variant:
            show_units_per = product_variant.show_units_per
            if show_units_per == 'pack' and tier_type != 'pack':
                raise serializers.ValidationError("Tier type must be 'pack' when show_units_per is 'Pack'.")
            if show_units_per == 'both' and tier_type not in ['pack', 'pallet']:
                raise serializers.ValidationError("Tier type must be 'pack' or 'pallet' when show_units_per is 'Both'.")

        # Validate mandatory starting range and sequential ranges
        if product_variant:
            instance = self.instance
            existing_tiers = PricingTier.objects.filter(
                product_variant=product_variant,
                tier_type=tier_type
            )
            if instance:
                existing_tiers = existing_tiers.exclude(id=instance.id)
            existing_tiers = existing_tiers.order_by('range_start')

            # Check if this is the first tier
            if not existing_tiers and range_start != 1:
                raise serializers.ValidationError(f"The first {tier_type} tier must start from 1.")

            # Check for overlaps and gaps
            current_end = float('inf') if no_end_range else range_end
            for tier in existing_tiers:
                tier_end = float('inf') if tier.no_end_range else tier.range_end
                if range_start <= tier_end and current_end >= tier.range_start:
                    raise serializers.ValidationError(
                        f"Range {range_start}-{'+' if no_end_range else range_end} overlaps with "
                        f"existing range {tier.range_start}-{'+' if tier.no_end_range else tier.range_end} for {tier_type}."
                    )

            # Check sequential ranges
            if existing_tiers:
                first_tier = existing_tiers.first()
                if first_tier.range_start != 1:
                    raise serializers.ValidationError(f"The first {tier_type} tier must start from 1.")
                sorted_tiers = list(existing_tiers)
                if not no_end_range and range_end:
                    sorted_tiers.append(PricingTier(
                        tier_type=tier_type,
                        range_start=range_start,
                        range_end=range_end,
                        no_end_range=no_end_range
                    ))
                    sorted_tiers.sort(key=lambda x: x.range_start)
                for i in range(len(sorted_tiers) - 1):
                    current = sorted_tiers[i]
                    next_tier = sorted_tiers[i + 1]
                    current_end = float('inf') if current.no_end_range else current.range_end
                    if not current.no_end_range and next_tier.range_start != current.range_end + 1:
                        raise serializers.ValidationError(
                            f"Range {range_start}-{'+' if no_end_range else range_end} creates a gap or is not sequential "
                            f"with existing ranges for {tier_type}. Ensure ranges are sequential with no gaps."
                        )

        return data

class ProductVariantSerializer(serializers.ModelSerializer):
    pricing_tiers = PricingTierSerializer(many=True, read_only=True)
    product = ProductSerializer(read_only=True)

    class Meta:
        model = ProductVariant
        fields = [
            'id', 'product', 'name',
            'show_units_per', 'created_at', 'pricing_tiers'
        ]

    def validate(self, data):
        show_units_per = data.get('show_units_per')

        # Validate pricing tiers if instance exists
        if self.instance and self.instance.pk:
            pricing_tiers = self.instance.pricing_tiers.all()
            pack_tiers = sorted([tier for tier in pricing_tiers if tier.tier_type == 'pack'], key=lambda x: x.range_start)
            pallet_tiers = [tier for tier in pricing_tiers if tier.tier_type == 'pallet']

            if show_units_per == 'pack':
                if not pack_tiers:
                    raise serializers.ValidationError("At least one 'pack' pricing tier is required when show_units_per is 'Pack'.")
                if pallet_tiers:
                    raise serializers.ValidationError("Pallet pricing tiers are not allowed when show_units_per is 'Pack'.")
                pack_no_end = [tier for tier in pack_tiers if tier.no_end_range]
                if len(pack_no_end) != 1:
                    raise serializers.ValidationError("Exactly one 'pack' pricing tier must have 'No End Range' checked.")
                # Validate pack tiers are sequential
                if pack_tiers:
                    if pack_tiers[0].range_start != 1:
                        raise serializers.ValidationError("The first 'pack' pricing tier must start from 1.")
                    for i in range(len(pack_tiers) - 1):
                        current = pack_tiers[i]
                        next_tier = pack_tiers[i + 1]
                        if not current.no_end_range and next_tier.range_start != current.range_end + 1:
                            raise serializers.ValidationError("Pack pricing tiers must be sequential with no gaps or overlaps.")
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
                # Validate pack tiers are sequential
                if pack_tiers:
                    if pack_tiers[0].range_start != 1:
                        raise serializers.ValidationError("The first 'pack' pricing tier must start from 1.")
                    for i in range(len(pack_tiers) - 1):
                        current = pack_tiers[i]
                        next_tier = pack_tiers[i + 1]
                        if not current.no_end_range and next_tier.range_start != current.range_end + 1:
                            raise serializers.ValidationError("Pack pricing tiers must be sequential with no gaps or overlaps.")

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
            'pricing_tier_data', 'data_entries', 'height', 'width', 'length', 'measurement_unit',
            'units_per_pack'
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
        units_per_pack = data.get('units_per_pack')

        product_variant = data.get('product_variant')
        if not product_variant and self.instance:
            product_variant = self.instance.product_variant

        if product_variant and product_variant.show_units_per == 'both' and not is_physical_product:
            raise serializers.ValidationError("Item must be a physical product when product variant show units per is set to 'both'.")

        # Validate units_per_pack
        if units_per_pack is None or units_per_pack <= 0:
            raise serializers.ValidationError("Units per pack must be provided and greater than 0.")

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
    total_weight_kg = serializers.SerializerMethodField()
    unit_type = serializers.CharField(default='pack')

    class Meta:
        model = CartItem
        fields = ['id', 'cart', 'item', 'pricing_tier', 'pack_quantity', 'unit_type', 
                 'user_exclusive_price', 'created_at', 'total_weight_kg']
        read_only_fields = ['created_at', 'total_weight_kg']

    def get_total_weight_kg(self, obj):
        return obj.total_weight_kg

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

        if 'user_exclusive_price' in data and data['user_exclusive_price']:
            user_exclusive_price = data['user_exclusive_price']
            if not isinstance(user_exclusive_price, (int, str)):
                raise serializers.ValidationError({
                    'user_exclusive_price': 'Expected ID, got object'
                })

        return data

    def create(self, validated_data):
        cart = validated_data.get('cart')
        item = validated_data.get('item')
        pricing_tier = validated_data.get('pricing_tier')
        pack_quantity = validated_data.get('pack_quantity', 1)
        unit_type = validated_data.get('unit_type', 'pack')
        user_exclusive_price = validated_data.get('user_exclusive_price')

        existing_cart_item = CartItem.objects.filter(
            cart=cart,
            item=item,
            unit_type=unit_type
        ).first()

        if existing_cart_item:
            existing_cart_item.pack_quantity = pack_quantity
            existing_cart_item.pricing_tier = pricing_tier
            existing_cart_item.user_exclusive_price = user_exclusive_price
            existing_cart_item.full_clean()
            existing_cart_item.save()
            existing_cart_item.cart.update_pricing_tiers()
            return existing_cart_item
        
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
        cart_item.cart.update_pricing_tiers()
        return cart_item

    def update(self, instance, validated_data):
        instance.pack_quantity = validated_data.get('pack_quantity', instance.pack_quantity)
        instance.pricing_tier = validated_data.get('pricing_tier', instance.pricing_tier)
        instance.user_exclusive_price = validated_data.get('user_exclusive_price', instance.user_exclusive_price)
        instance.unit_type = validated_data.get('unit_type', instance.unit_type)
        instance.full_clean()
        instance.save()
        instance.cart.update_pricing_tiers()
        return instance

class CartItemDetailSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)  # Explicitly define the item field to use ItemSerializer

    class Meta:
        model = CartItem
        fields = ['id', 'cart', 'item', 'pricing_tier', 'pack_quantity', 'unit_type', 'user_exclusive_price', 'created_at']
        read_only_fields = ['created_at', 'unit_type']

    def get_discount_percentage(self, obj):
        return obj.user_exclusive_price.discount_percentage if obj.user_exclusive_price else Decimal('0.00')

    def get_price_per_unit(self, obj):
        pricing_data = PricingTierData.objects.filter(pricing_tier=obj.pricing_tier, item=obj.item).first()
        return pricing_data.price if pricing_data else Decimal('0.00')

    def get_price_per_pack(self, obj):
        pricing_data = PricingTierData.objects.filter(pricing_tier=obj.pricing_tier, item=obj.item).first()
        if pricing_data and obj.item:
            return pricing_data.price * Decimal(obj.item.units_per_pack or 1)
        return Decimal('0.00')

    def get_subtotal(self, obj):
        pricing_data = PricingTierData.objects.filter(pricing_tier=obj.pricing_tier, item=obj.item).first()
        if pricing_data and obj.item:
            units_per_pack = obj.item.units_per_pack or 1
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
            'discount_percentage': self.get_discount_percentage(instance),
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

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', [])
        existing_items = {
            (item.item_id, item.unit_type): item 
            for item in instance.items.all()
        }
        
        with transaction.atomic():
            for item_data in items_data:
                key = (
                    item_data['item'].id,
                    item_data.get('unit_type', 'pack')
                )
                
                if key in existing_items:
                    existing_item = existing_items[key]
                    existing_item.pack_quantity = item_data['pack_quantity']
                    existing_item.pricing_tier = item_data['pricing_tier']
                    existing_item.user_exclusive_price = item_data.get(
                        'user_exclusive_price',
                        existing_item.user_exclusive_price
                    )
                    existing_item.full_clean()
                    existing_item.save()
                else:
                    CartItem.objects.create(cart=instance, **item_data)
            
            instance.update_pricing_tiers()
        
        return instance

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
        if pricing_data and obj.item:
            return pricing_data.price * Decimal(obj.item.units_per_pack or 1)
        return Decimal('0.00')

    def get_subtotal(self, obj):
        pricing_data = PricingTierData.objects.filter(pricing_tier=obj.pricing_tier, item=obj.item).first()
        if pricing_data and obj.item:
            units_per_pack = obj.item.units_per_pack or 1
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

class ShippingAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShippingAddress
        fields = ['id', 'first_name', 'last_name', 'telephone_number', 'street', 'city', 'state', 'postal_code', 'country']
        read_only_fields = ['id', 'created_at', 'updated_at']

class BillingAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = BillingAddress
        fields = ['id', 'first_name', 'last_name', 'telephone_number', 'street', 'city', 'state', 'postal_code', 'country']
        read_only_fields = ['id', 'created_at', 'updated_at']

class OrderItemDetailSerializer(serializers.ModelSerializer):
    item = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = ['id', 'order', 'item', 'pricing_tier', 'pack_quantity', 'unit_type', 'user_exclusive_price', 'created_at']
        read_only_fields = ['created_at', 'unit_type']

    def get_item(self, obj):
        from ecommerce.serializers import ItemSerializer
        return ItemSerializer(obj.item, context=self.context).data

    def get_price_per_unit(self, obj):
        pricing_data = PricingTierData.objects.filter(pricing_tier=obj.pricing_tier, item=obj.item).first()
        return pricing_data.price if pricing_data else Decimal('0.00')

    def get_price_per_pack(self, obj):
        pricing_data = PricingTierData.objects.filter(pricing_tier=obj.pricing_tier, item=obj.item).first()
        if pricing_data and obj.item:
            return pricing_data.price * Decimal(obj.item.units_per_pack or 1)
        return Decimal('0.00')

    def get_subtotal(self, obj):
        pricing_data = PricingTierData.objects.filter(pricing_tier=obj.pricing_tier, item=obj.item).first()
        if pricing_data and obj.item:
            units_per_pack = obj.item.units_per_pack or 1
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
    shipping_address = serializers.PrimaryKeyRelatedField(
        queryset=ShippingAddress.objects.all(),
        required=True,
        allow_null=False
    )
    billing_address = serializers.PrimaryKeyRelatedField(
        queryset=BillingAddress.objects.all(),
        required=True,
        allow_null=False
    )
    shipping_address_detail = ShippingAddressSerializer(source='shipping_address', read_only=True)
    billing_address_detail = BillingAddressSerializer(source='billing_address', read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'user', 'shipping_address', 'billing_address',
            'shipping_address_detail', 'billing_address_detail',
            'shipping_cost', 'vat', 'discount', 'status', 'payment_status',
            'payment_method', 'payment_verified', 'transaction_id',
            'payment_receipt', 'refund_transaction_id', 'refund_payment_receipt',
            'paid_receipt', 'refund_receipt', 'invoice', 'delivery_note',
            'created_at', 'updated_at', 'items'
        ]
        read_only_fields = [
            'id', 'user', 'items', 'created_at', 'updated_at',
            'shipping_address_detail', 'billing_address_detail',
            'payment_method', 'shipping_cost', 'vat', 'discount',
            'invoice', 'delivery_note', 'paid_receipt', 'refund_receipt',
            'transaction_id', 'payment_receipt'
        ]

    def validate_status(self, value):
        status_map = {
            'pending': 'PENDING',
            'processing': 'PROCESSING',
            'shipped': 'SHIPPED',
            'delivered': 'DELIVERED',
            'cancelled': 'CANCELLED',
            'returned': 'RETURNED'
        }
        normalized = value.upper() if value else value
        if normalized in status_map:
            normalized = status_map[normalized]
        if normalized not in dict(Order.STATUS_CHOICES):
            raise serializers.ValidationError(f'"{value}" is not a valid choice.')
        return normalized

    def validate_payment_status(self, value):
        payment_status_map = {
            'pending': 'PENDING',
            'completed': 'COMPLETED',
            'failed': 'FAILED',
            'refund': 'REFUND'
        }
        normalized = value.upper() if value else value
        if normalized in payment_status_map:
            normalized = payment_status_map[normalized]
        if normalized not in dict(Order.PAYMENT_STATUS_CHOICES):
            raise serializers.ValidationError(f'"{value}" is not a valid choice.')
        return normalized

    def validate(self, data):
        logger.info(f"Raw input data: {self.initial_data}")
        logger.info(f"Validated data: {data}")
        payment_status = data.get('payment_status', self.instance.payment_status if self.instance else 'PENDING')
        payment_verified = data.get('payment_verified', self.instance.payment_verified if self.instance else False)

        errors = {}
        if payment_verified:
            if payment_status == 'PENDING' or payment_status == 'FAILED':
                errors['payment_status'] = 'Payment status must be COMPLETED/REFUNDED when payment is verified.'
            if not data.get('transaction_id') and not (self.instance and self.instance.transaction_id):
                errors['transaction_id'] = 'Transaction ID is required when payment is verified.'
            if not data.get('payment_receipt') and not (self.instance and self.instance.payment_receipt):
                errors['payment_receipt'] = 'Payment receipt is required when payment is verified.'
        if payment_status == 'COMPLETED':
            if not data.get('transaction_id') and not (self.instance and self.instance.transaction_id):
                errors['transaction_id'] = 'Transaction ID is required when payment status is Completed.'
            if not data.get('payment_receipt') and not (self.instance and self.instance.payment_receipt):
                errors['payment_receipt'] = 'Payment receipt is required when payment status is Completed.'
        elif payment_status == 'REFUND':
            if not data.get('transaction_id') and not (self.instance and self.instance.transaction_id):
                errors['transaction_id'] = 'Transaction ID is required when payment status is Refunded.'
            if not data.get('payment_receipt') and not (self.instance and self.instance.payment_receipt):
                errors['payment_receipt'] = 'Payment receipt is required when payment status is Refunded.'
            if not data.get('refund_transaction_id') and not (self.instance and self.instance.refund_transaction_id):
                errors['refund_transaction_id'] = 'Refunded transaction ID is required when payment status is Refunded.'
            if not data.get('refund_payment_receipt') and not (self.instance and self.instance.refund_payment_receipt):
                errors['refund_payment_receipt'] = 'Refunded payment receipt is required when payment status is Refunded.'
        if errors:
            raise serializers.ValidationError(errors)

        return data

    def create(self, validated_data):
        logger.info(f"Creating order with validated data: {validated_data}")
        user = self.context['request'].user
        if not user.is_authenticated:
            raise PermissionDenied("Authentication required to create an order.")
        validated_data['user'] = user
        validated_data['payment_method'] = 'manual_payment'

        with transaction.atomic():
            order = super().create(validated_data)
            logger.info(f"Order {order.id} created for user {user.id}")

            from .models import Cart, CartItem
            cart = Cart.objects.filter(user=user).first()
            if cart and cart.items.exists():
                for cart_item in cart.items.all():
                    if cart_item.item and cart_item.pricing_tier and cart_item.pack_quantity:
                        user_exclusive_price = cart_item.user_exclusive_price  # Use only if exists
                        OrderItem.objects.create(
                            order=order,
                            item=cart_item.item,
                            pricing_tier=cart_item.pricing_tier,
                            pack_quantity=cart_item.pack_quantity,
                            unit_type=cart_item.unit_type,
                            user_exclusive_price=user_exclusive_price
                        )
                        logger.info(f"Created OrderItem for order {order.id}, item {cart_item.item.id}")
                    else:
                        logger.warning(f"Skipping invalid cart item for order {order.id}: {cart_item}")
                cart.items.all().delete()
                logger.info(f"Cleared cart for user {user.id}")
            else:
                logger.warning(f"No valid cart items found for user {user.id} during order {order.id} creation")

            order.calculate_total()
            order.generate_and_save_pdfs()
            if order.payment_verified or order.payment_status in ['COMPLETED', 'REFUND']:
                order.generate_and_save_payment_receipts()
            logger.info(f"PDFs and receipts generated for order {order.id}")

            return order

    def update(self, instance, validated_data):
        logger.info(f"Updating order {instance.id} with validated data: {validated_data}")
        with transaction.atomic():
            order = super().update(instance, validated_data)
            order.calculate_total()
            if order.items.exists():
                order.generate_and_save_pdfs()
                if order.payment_verified or order.payment_status in ['COMPLETED', 'REFUND']:
                    order.generate_and_save_payment_receipts()
            logger.info(f"Order {order.id} updated with PDFs and receipts")
            return order

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
                'shipping_address': None,
                'billing_address': None,
                'shipping_address_detail': None,
                'billing_address_detail': None,
                'shipping_cost': str(Decimal('0.00')),
                'vat': str(Decimal('0.00')),
                'discount': str(Decimal('0.00')),
                'status': 'PENDING',
                'payment_status': 'PENDING',
                'payment_method': 'manual_payment',
                'payment_verified': False,
                'transaction_id': None,
                'payment_receipt': None,
                'refund_transaction_id': None,
                'refund_payment_receipt': None,
                'paid_receipt': None,
                'refund_receipt': None,
                'invoice': None,
                'delivery_note': None,
                'items': [],
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
            'shipping_cost': str(instance.shipping_cost),
            'subtotal': str(self.get_subtotal(instance)),
            'total': str(self.get_total(instance)),
            'total_weight': str(self.get_total_weight(instance)),
            'total_units': self.get_total_units(instance),
            'total_packs': self.get_total_packs(instance),
        })
        return representation