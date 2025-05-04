from rest_framework import serializers
from ecommerce.models import (
    Category, Product, ProductImage, ProductVariant, PricingTier, PricingTierData,
    TableField, Item, ItemImage, ItemData, UserExclusivePrice, Cart, CartItem, Order, OrderItem
)
from decimal import Decimal, ROUND_HALF_UP

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
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.all())
    pricing_tier = serializers.PrimaryKeyRelatedField(queryset=PricingTier.objects.all())
    user_exclusive_price = serializers.PrimaryKeyRelatedField(queryset=UserExclusivePrice.objects.all(), required=False, allow_null=True)

    class Meta:
        model = CartItem
        fields = ['id', 'cart', 'item', 'pricing_tier', 'quantity', 'unit_type', 'per_unit_price', 'per_pack_price', 'subtotal', 'total_cost', 'user_exclusive_price', 'created_at']
        read_only_fields = ['created_at', 'per_unit_price', 'per_pack_price', 'subtotal', 'total_cost']

    def validate(self, data):
        instance_data = {
            'cart': data.get('cart'),
            'item': data.get('item'),
            'pricing_tier': data.get('pricing_tier'),
            'quantity': data.get('quantity'),
            'unit_type': data.get('unit_type'),
            'user_exclusive_price': data.get('user_exclusive_price'),
        }
        instance = CartItem(**instance_data)

        pricing_data = PricingTierData.objects.filter(
            pricing_tier=instance.pricing_tier,
            item=instance.item
        ).first()
        if not pricing_data:
            raise serializers.ValidationError("No pricing data found for this item and pricing tier.")

        units_per_pack = instance.item.product_variant.units_per_pack
        units_per_pallet = instance.item.product_variant.units_per_pallet
        per_unit_price = pricing_data.price
        per_pack_price = per_unit_price * Decimal(units_per_pack)

        if instance.unit_type == 'pack':
            if instance.pricing_tier.tier_type == 'pack':
                subtotal = per_pack_price * Decimal(instance.quantity)
            else:
                total_units = Decimal(instance.quantity) * Decimal(units_per_pack)
                equivalent_pallet_quantity = total_units / Decimal(units_per_pallet)
                subtotal = equivalent_pallet_quantity * per_pack_price * Decimal(units_per_pallet) / Decimal(units_per_pack)
        else:
            total_units = Decimal(instance.quantity) * Decimal(units_per_pallet)
            equivalent_pack_quantity = total_units / Decimal(units_per_pack)
            subtotal = equivalent_pack_quantity * per_pack_price
        subtotal = subtotal.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        discount_percentage = instance.user_exclusive_price.discount_percentage if instance.user_exclusive_price else Decimal('0.00')
        discount = discount_percentage / Decimal('100.00')
        total_cost = subtotal * (Decimal('1.00') - discount)
        total_cost = total_cost.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        data['per_unit_price'] = per_unit_price
        data['per_pack_price'] = per_pack_price
        data['subtotal'] = subtotal
        data['total_cost'] = total_cost

        self.context['calculated_fields'] = {
            'per_unit_price': per_unit_price,
            'per_pack_price': per_pack_price,
            'subtotal': subtotal,
            'total_cost': total_cost,
        }

        if instance.quantity <= 0:
            raise serializers.ValidationError("Quantity must be positive.")
        if instance.unit_type not in ['pack', 'pallet']:
            raise serializers.ValidationError("Unit type must be 'pack' or 'pallet'.")
        if instance.pricing_tier.product_variant != instance.item.product_variant:
            raise serializers.ValidationError("Pricing tier must belong to the same product variant as the item.")
        if instance.item.product_variant.show_units_per == 'pack' and instance.unit_type == 'pallet':
            raise serializers.ValidationError("This item only supports pack pricing, not pallet pricing.")
        if instance.user_exclusive_price:
            if instance.user_exclusive_price.item != instance.item:
                raise serializers.ValidationError("User exclusive price must correspond to the selected item.")
            if instance.user_exclusive_price.user != instance.cart.user:
                raise serializers.ValidationError("User exclusive price must correspond to the cart's user.")

        return data

    def create(self, validated_data):
        cart = validated_data['cart']
        item = validated_data['item']
        pricing_tier = validated_data['pricing_tier']
        unit_type = validated_data['unit_type']

        existing_cart_item = CartItem.objects.filter(
            cart=cart,
            item=item,
            pricing_tier=pricing_tier,
            unit_type=unit_type
        ).first()

        calculated_fields = self.context.get('calculated_fields', {})
        per_unit_price = calculated_fields.get('per_unit_price', validated_data.get('per_unit_price'))
        per_pack_price = calculated_fields.get('per_pack_price', validated_data.get('per_pack_price'))
        subtotal = calculated_fields.get('subtotal', validated_data.get('subtotal'))
        total_cost = calculated_fields.get('total_cost', validated_data.get('total_cost'))

        if existing_cart_item:
            existing_cart_item.quantity += validated_data['quantity']
            existing_cart_item.per_unit_price = per_unit_price
            existing_cart_item.per_pack_price = per_pack_price
            existing_cart_item.subtotal = subtotal
            existing_cart_item.total_cost = total_cost
            existing_cart_item.user_exclusive_price = validated_data.get('user_exclusive_price')
            existing_cart_item.save()
            return existing_cart_item
        else:
            cart_item = CartItem(
                cart=cart,
                item=item,
                pricing_tier=pricing_tier,
                quantity=validated_data['quantity'],
                unit_type=unit_type,
                per_unit_price=per_unit_price,
                per_pack_price=per_pack_price,
                subtotal=subtotal,
                total_cost=total_cost,
                user_exclusive_price=validated_data.get('user_exclusive_price')
            )
            cart_item.save()
            return cart_item

    def update(self, instance, validated_data):
        calculated_fields = self.context.get('calculated_fields', {})
        instance.quantity = validated_data.get('quantity', instance.quantity)
        instance.unit_type = validated_data.get('unit_type', instance.unit_type)
        instance.per_unit_price = calculated_fields.get('per_unit_price', validated_data.get('per_unit_price', instance.per_unit_price))
        instance.per_pack_price = calculated_fields.get('per_pack_price', validated_data.get('per_pack_price', instance.per_pack_price))
        instance.subtotal = calculated_fields.get('subtotal', validated_data.get('subtotal', instance.subtotal))
        instance.total_cost = calculated_fields.get('total_cost', validated_data.get('total_cost', instance.total_cost))
        instance.user_exclusive_price = validated_data.get('user_exclusive_price', instance.user_exclusive_price)
        instance.save()
        return instance

class CartItemDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = CartItem
        fields = ['id', 'cart', 'item', 'pricing_tier', 'quantity', 'unit_type', 'per_unit_price', 'per_pack_price', 'subtotal', 'total_cost', 'user_exclusive_price', 'created_at']
        depth = 4

class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)

    class Meta:
        model = Cart
        fields = ['id', 'user', 'items', 'subtotal', 'vat', 'discount', 'total', 'created_at', 'updated_at']
        read_only_fields = ['id', 'user', 'subtotal', 'total', 'created_at', 'updated_at']

class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ['id', 'order', 'item', 'pricing_tier', 'quantity', 'unit_type', 'per_unit_price', 'per_pack_price', 'total_cost', 'user_exclusive_price', 'created_at']
        read_only_fields = ['created_at', 'per_unit_price', 'per_pack_price', 'total_cost']

    def validate(self, data):
        instance = OrderItem(**data)
        
        pricing_data = PricingTierData.objects.filter(
            pricing_tier=instance.pricing_tier,
            item=instance.item
        ).first()
        if not pricing_data:
            raise serializers.ValidationError("No pricing data found for this item and pricing tier.")

        units_per_pack = instance.item.product_variant.units_per_pack
        units_per_pallet = instance.item.product_variant.units_per_pallet
        per_unit_price = pricing_data.price
        per_pack_price = per_unit_price * Decimal(units_per_pack)

        if instance.unit_type == 'pack':
            total_cost = per_pack_price * Decimal(instance.quantity)
        else:
            total_units = Decimal(instance.quantity) * Decimal(units_per_pallet)
            equivalent_pack_quantity = total_units / Decimal(units_per_pack)
            total_cost = equivalent_pack_quantity * per_pack_price
        total_cost = total_cost.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        data['per_unit_price'] = per_unit_price
        data['per_pack_price'] = per_pack_price
        data['total_cost'] = total_cost

        if instance.quantity <= 0:
            raise serializers.ValidationError("Quantity must be positive.")
        if instance.unit_type not in ['pack', 'pallet']:
            raise serializers.ValidationError("Unit type must be 'pack' or 'pallet'.")
        if instance.pricing_tier.product_variant != instance.item.product_variant:
            raise serializers.ValidationError("Pricing tier must belong to the same product variant as the item.")
        if instance.item.product_variant.show_units_per == 'pack' and instance.unit_type == 'pallet':
            raise serializers.ValidationError("This item only supports pack pricing, not pallet pricing.")
        if instance.user_exclusive_price:
            if instance.user_exclusive_price.item != instance.item:
                raise serializers.ValidationError("User exclusive price must correspond to the selected item.")
            if instance.user_exclusive_price.user != instance.order.user:
                raise serializers.ValidationError("User exclusive price must correspond to the order's user.")

        return data 

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