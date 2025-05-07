from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import action
from ecommerce.models import (
    Category, Product, ProductImage, ProductVariant, PricingTier, PricingTierData,
    TableField, Item, ItemImage, ItemData, UserExclusivePrice, Cart, CartItem, Order, OrderItem
)
from ecommerce.serializers import (
    CategorySerializer, ProductImageSerializer, ProductSerializer, ProductVariantSerializer,
    PricingTierSerializer, PricingTierDataSerializer, TableFieldSerializer, ItemSerializer,
    ItemImageSerializer, ItemDataSerializer, UserExclusivePriceSerializer,
    CartSerializer, CartItemSerializer, OrderSerializer, OrderItemSerializer, CartItemDetailSerializer
)
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank, SearchHeadline
from django.db.models import Q
from decimal import Decimal
from rest_framework.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.db import transaction

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['name']

    def get_queryset(self):
        queryset = super().get_queryset()
        search_query = self.request.query_params.get('search', None)
        slug = self.request.query_params.get('slug', None)
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query) |
                Q(slug__icontains=search_query) |
                Q(description__icontains=search_query)
            )
        if slug:
            queryset = queryset.filter(slug=slug)
        return queryset

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [AllowAny()]

class ProductImageViewSet(viewsets.ModelViewSet):
    queryset = ProductImage.objects.all()
    serializer_class = ProductImageSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['product']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [AllowAny()]

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all().select_related('category').prefetch_related('images')
    serializer_class = ProductSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['name', 'slug', 'is_new']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [AllowAny()]

    def get_queryset(self):
        queryset = super().get_queryset()
        category_slug = self.request.query_params.get('category')
        slug = self.request.query_params.get('slug')
        search_query = self.request.query_params.get('search')

        if category_slug:
            try:
                category = Category.objects.get(slug=category_slug)
                queryset = queryset.filter(category=category)
            except Category.DoesNotExist:
                queryset = queryset.none()

        if slug:
            queryset = queryset.filter(slug=slug)

        if search_query:
            search_query = search_query.strip()
            if search_query:
                raw_query = search_query
                ts_query = ' '.join(search_query.split())
                search_query_obj = SearchQuery(ts_query, config='english', search_type='plain')
                search_vector = SearchVector('name', weight='A') + SearchVector('description', weight='B')
                search_rank = SearchRank(search_vector, search_query_obj)
                search_headline = SearchHeadline(
                    'description',
                    search_query_obj,
                    max_words=35,
                    min_words=15,
                    start_sel='<b>',
                    stop_sel='</b>',
                    config='english'
                )
                queryset = queryset.annotate(
                    search=search_vector,
                    rank=search_rank,
                    headline=search_headline
                ).filter(
                    search=search_query_obj
                ).filter(
                    Q(name__icontains=raw_query) | Q(description__icontains=raw_query)
                ).order_by('-rank')

        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        search_query = self.request.query_params.get('search')
        if search_query and 'queryset' in context:
            context['search_headline'] = {
                obj.id: obj.headline for obj in context['queryset']
                if hasattr(obj, 'headline')
            }
        return context

class ProductVariantViewSet(viewsets.ModelViewSet):
    queryset = ProductVariant.objects.filter(status="active").select_related('product').prefetch_related('pricing_tiers__pricing_data')
    serializer_class = ProductVariantSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['product', 'name']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [AllowAny()]

    @action(detail=True, methods=['get'], url_path='calculate-price')
    def calculate_price(self, request, pk=None):
        product_variant = self.get_object()
        units = int(request.query_params.get('units', 0))
        price_per = request.query_params.get('price_per', 'pack')  # 'pack' or 'pallet'

        if units <= 0:
            return Response({"error": "Units must be greater than 0"}, status=status.HTTP_400_BAD_REQUEST)

        units_per_pack = product_variant.units_per_pack
        units_per_pallet = product_variant.units_per_pallet
        show_units_per = product_variant.show_units_per

        packs = 0
        pallets = 0
        if show_units_per in ['pack', 'both']:
            packs = units // units_per_pack
            remaining_units = units % units_per_pack
            if remaining_units > 0:
                packs += 1
        if show_units_per in ['pallet', 'both']:
            pallets = units // units_per_pallet
            remaining_units = units % units_per_pallet
            if remaining_units > 0:
                pallets += 1

        try:
            item = product_variant.items.first()
            if not item:
                return Response({"error": "No items found for this product variant"}, status=status.HTTP_400_BAD_REQUEST)
        except Item.DoesNotExist:
            return Response({"error": "No items found for this product variant"}, status=status.HTTP_400_BAD_REQUEST)

        total = Decimal('0.00')
        if show_units_per in ['pack', 'both'] and price_per == 'pack':
            tiers = product_variant.pricing_tiers.filter(tier_type='pack').order_by('range_start')
            applicable_tier = None
            for tier in tiers:
                range_end = tier.range_end if tier.range_end is not None else float('inf')
                if packs >= tier.range_start and packs <= range_end:
                    applicable_tier = tier
                    break
            if applicable_tier:
                try:
                    pricing_data = PricingTierData.objects.get(item=item, pricing_tier=applicable_tier)
                    total = packs * pricing_data.price
                except PricingTierData.DoesNotExist:
                    return Response({"error": f"No pricing data found for tier {applicable_tier}"}, status=status.HTTP_400_BAD_REQUEST)
        elif show_units_per in ['pallet', 'both'] and price_per == 'pallet':
            tiers = product_variant.pricing_tiers.filter(tier_type='pallet').order_by('range_start')
            applicable_tier = None
            for tier in tiers:
                range_end = tier.range_end if tier.range_end is not None else float('inf')
                if pallets >= tier.range_start and pallets <= range_end:
                    applicable_tier = tier
                    break
            if applicable_tier:
                try:
                    pricing_data = PricingTierData.objects.get(item=item, pricing_tier=applicable_tier)
                    total = pallets * pricing_data.price
                except PricingTierData.DoesNotExist:
                    return Response({"error": f"No pricing data found for tier {applicable_tier}"}, status=status.HTTP_400_BAD_REQUEST)
        else:
            tiers = product_variant.pricing_tiers.filter(tier_type='pack').order_by('range_start')
            applicable_tier = None
            for tier in tiers:
                range_end = tier.range_end if tier.range_end is not None else float('inf')
                if packs >= tier.range_start and packs <= range_end:
                    applicable_tier = tier
                    break
            if applicable_tier:
                try:
                    pricing_data = PricingTierData.objects.get(item=item, pricing_tier=applicable_tier)
                    price_per_unit = pricing_data.price / units_per_pack
                    total = units * price_per_unit
                except PricingTierData.DoesNotExist:
                    return Response({"error": f"No pricing data found for tier {applicable_tier}"}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'units': units,
            'packs': packs,
            'pallets': pallets,
            'total': float(total)
        })

class PricingTierViewSet(viewsets.ModelViewSet):
    queryset = PricingTier.objects.all().select_related('product_variant').prefetch_related('pricing_data')
    serializer_class = PricingTierSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['product_variant', 'tier_type']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [AllowAny()]

class PricingTierDataViewSet(viewsets.ModelViewSet):
    queryset = PricingTierData.objects.all().select_related('item__product_variant', 'pricing_tier')
    serializer_class = PricingTierDataSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['item', 'pricing_tier']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [AllowAny()]

class TableFieldViewSet(viewsets.ModelViewSet):
    queryset = TableField.objects.all().select_related('product_variant')
    serializer_class = TableFieldSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['product_variant', 'field_type']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [AllowAny()]

class ItemImageViewSet(viewsets.ModelViewSet):
    queryset = ItemImage.objects.all()
    serializer_class = ItemImageSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['item']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [AllowAny()]

class ItemViewSet(viewsets.ModelViewSet):
    queryset = Item.objects.all().select_related('product_variant__product__category').prefetch_related('data_entries__field', 'images', 'pricing_tier_data')
    serializer_class = ItemSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['product_variant', 'sku', 'status']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [AllowAny()]

    def get_queryset(self):
        queryset = super().get_queryset()
        width = self.request.query_params.get('width')
        length = self.request.query_params.get('length')
        height = self.request.query_params.get('height')
        measurement_unit = self.request.query_params.get('measurement_unit', '').upper()
        category = self.request.query_params.get('category')
        approx_size = self.request.query_params.get('approx_size', '').lower() == 'true'
        minimum_size = self.request.query_params.get('minimum_size', '').lower() == 'true'

        valid_units = ['MM', 'CM', 'IN', 'M']
        if measurement_unit and measurement_unit not in valid_units:
            return queryset.none()

        if category:
            category = category.lower()
            valid_categories = ['box', 'boxes', 'bag', 'bags', 'postal', 'postals']
            if category in valid_categories:
                queryset = queryset.filter(product_variant__product__category__name__iexact=category)
            else:
                return queryset.none()

        if width and length and height:
            try:
                width = Decimal(width)
                length = Decimal(length)
                height = Decimal(height)
            except (ValueError, TypeError):
                return queryset.none()

            to_inches = {
                'MM': Decimal('0.0393701'),
                'CM': Decimal('0.393701'),
                'IN': Decimal('1.0'),
                'M': Decimal('39.3701'),
            }
            from_inches = {
                'MM': Decimal('25.4'),
                'CM': Decimal('2.54'),
                'IN': Decimal('1.0'),
                'M': Decimal('0.0254'),
            }

            dimension_filter = Q()
            for item in queryset:
                item_width = item.width
                item_length = item.length
                item_height = item.height
                item_unit = item.measurement_unit

                if item_width is None or item_length is None or item_height is None or not item_unit:
                    continue

                if item_unit != measurement_unit and measurement_unit:
                    item_width = item_width * to_inches[item_unit]
                    item_length = item_length * to_inches[item_unit]
                    item_height = item_height * to_inches[item_unit]
                    item_width = item_width * from_inches[measurement_unit]
                    item_length = item_length * from_inches[measurement_unit]
                    item_height = item_height * from_inches[measurement_unit]

                if approx_size:
                    width_min = width * Decimal('0.9')
                    width_max = width * Decimal('1.1')
                    length_min = length * Decimal('0.9')
                    length_max = length * Decimal('1.1')
                    height_min = height * Decimal('0.9')
                    height_max = height * Decimal('1.1')
                    dimension_filter |= Q(
                        id=item.id,
                        width__gte=width_min, width__lte=width_max,
                        length__gte=length_min, length__lte=length_max,
                        height__gte=height_min, height__lte=height_max
                    )
                elif minimum_size:
                    dimension_filter |= Q(
                        id=item.id,
                        width__gte=width,
                        length__gte=length,
                        height__gte=height
                    )
                else:
                    tolerance = Decimal('0.01')
                    dimension_filter |= Q(
                        id=item.id,
                        width__gte=width - tolerance, width__lte=width + tolerance,
                        length__gte=length - tolerance, length__lte=length + tolerance,
                        height__gte=height - tolerance, height__lte=height + tolerance
                    )

            queryset = queryset.filter(dimension_filter)

        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context.update({'request': self.request})
        return context

class ItemDataViewSet(viewsets.ModelViewSet):
    queryset = ItemData.objects.all().select_related('item__product_variant', 'field')
    serializer_class = ItemDataSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['item', 'field', 'field__field_type']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [AllowAny()]

class UserExclusivePriceViewSet(viewsets.ModelViewSet):
    queryset = UserExclusivePrice.objects.all().select_related('user', 'item__product_variant')
    serializer_class = UserExclusivePriceSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['user', 'item']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

class CartViewSet(viewsets.ModelViewSet):
    queryset = Cart.objects.all()
    serializer_class = CartSerializer
    permission_classes = [IsAuthenticated]

    def list(self, request, *args, **kwargs):
        """
        Retrieve the authenticated user's cart.
        """
        if not request.user.is_authenticated:
            raise PermissionDenied("Authentication required to access cart.")
        try:
            cart, created = Cart.get_or_create_cart(request.user)
            serializer = self.get_serializer(cart)
            return Response(serializer.data)
        except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def get_queryset(self):
        """
        Return the cart for the authenticated user.
        """
        if not self.request.user.is_authenticated:
            raise PermissionDenied("Authentication required to access cart.")
        return self.queryset.filter(user=self.request.user)

    @action(detail=False, methods=['delete'], url_path='clear')
    def clear_cart(self, request):
        """
        Clear all items from the user's cart.
        """
        if not request.user.is_authenticated:
            raise PermissionDenied("Authentication required to clear cart.")
        try:
            cart, created = Cart.get_or_create_cart(request.user)
            cart.items.all().delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class CartItemViewSet(viewsets.ModelViewSet):
    queryset = CartItem.objects.all()
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve']:
            return CartItemDetailSerializer
        return CartItemSerializer

    def create(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied("Authentication required to add cart items.")
        try:
            cart, created = Cart.get_or_create_cart(request.user)
            data = request.data.copy() if isinstance(request.data, dict) else request.data
            if isinstance(data, list):
                responses = []
                with transaction.atomic():
                    for item_data in data:
                        item_data['cart'] = cart.id
                        responses.append(self._process_cart_item(item_data, cart))
                return Response(responses, status=status.HTTP_200_OK)
            else:
                data['cart'] = cart.id
                response = self._process_cart_item(data, cart)
                return Response(response, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def _process_cart_item(self, data, cart):
        item_id = data.get('item')
        pricing_tier_id = data.get('pricing_tier')
        pack_quantity = data.get('pack_quantity', 1)
        user_exclusive_price_id = data.get('user_exclusive_price')

        if not item_id:
            raise ValidationError({"item": "Item ID is required."})

        item = Item.objects.get(id=item_id)
        pricing_tier = PricingTier.objects.get(id=pricing_tier_id)

        existing_cart_item = CartItem.objects.filter(
            cart=cart,
            item=item,
        ).first()

        serializer_context = {'request': self.request}
        if existing_cart_item:
            existing_cart_item.pack_quantity = pack_quantity
            existing_cart_item.pricing_tier = pricing_tier
            if user_exclusive_price_id:
                existing_cart_item.user_exclusive_price = UserExclusivePrice.objects.filter(
                    id=user_exclusive_price_id,
                    user=cart.user,
                    item=item
                ).first()
            else:
                existing_cart_item.user_exclusive_price = None
            existing_cart_item.full_clean()
            existing_cart_item.save()
            serializer = CartItemDetailSerializer(existing_cart_item, context=serializer_context)
        else:
            cart_item_data = {
                'cart': cart,
                'item': item,
                'pricing_tier': pricing_tier,
                'pack_quantity': pack_quantity,
                'unit_type': 'pack',
                'user_exclusive_price': UserExclusivePrice.objects.filter(
                    id=user_exclusive_price_id,
                    user=cart.user,
                    item=item
                ).first() if user_exclusive_price_id else None
            }
            cart_item = CartItem(**cart_item_data)
            cart_item.full_clean()
            cart_item.save()
            serializer = CartItemDetailSerializer(cart_item, context=serializer_context)

        return serializer.data

    def update(self, request, *args, **kwargs):
        pk = kwargs.get('pk')
        try:
            instance = self.get_queryset().get(pk=pk)
        except CartItem.DoesNotExist:
            return Response(
                {"detail": "Cart item not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        if instance.item is None:
            instance.delete()
            return Response(
                {"detail": "Cart item has no associated item and has been deleted."},
                status=status.HTTP_410_GONE
            )

        # Ignore 'item' field in request data to prevent updates to it
        request_data = request.data.copy()
        if 'item' in request_data:
            del request_data['item']

        serializer = self.get_serializer(instance, data=request_data, partial=True)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        instance.pack_quantity = validated_data.get('pack_quantity', instance.pack_quantity)
        instance.pricing_tier = validated_data.get('pricing_tier', instance.pricing_tier)
        instance.user_exclusive_price = validated_data.get('user_exclusive_price', instance.user_exclusive_price)

        try:
            instance.full_clean()
            instance.save()
        except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        response_serializer = CartItemDetailSerializer(instance, context={'request': request})
        return Response(response_serializer.data, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
        except CartItem.DoesNotExist:
            return Response(
                {"detail": "Cart item not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        if instance.item is None:
            instance.delete()
            return Response(
                {"detail": "Cart item has no associated item and has been deleted."},
                status=status.HTTP_410_GONE
            )

        serializer = self.get_serializer(instance)
        return Response(serializer.data)

class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all().select_related('user').prefetch_related('items__item', 'items__pricing_tier')
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['user', 'status', 'payment_status']

    def get_queryset(self):
        if self.request.user.is_staff:
            return self.queryset
        return self.queryset.filter(user=self.request.user)

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class OrderItemViewSet(viewsets.ModelViewSet):
    queryset = OrderItem.objects.all().select_related('order__user', 'item', 'pricing_tier')
    serializer_class = OrderItemSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['order', 'item', 'unit_type']

    def get_queryset(self):
        if self.request.user.is_staff:
            return self.queryset
        return self.queryset.filter(order__user=self.request.user)

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated()]
        return [IsAuthenticated()]