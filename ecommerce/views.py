from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from ecommerce.models import (
    Category, Product, ProductImage, ProductVariant, PricingTier, PricingTierData,
    TableField, Item, ItemImage, ItemData, UserExclusivePrice, Cart, CartItem, Order, OrderItem, ShippingAddress, BillingAddress
)
from ecommerce.serializers import (
    CategorySerializer, ProductImageSerializer, ProductSerializer, ProductVariantSerializer,
    PricingTierSerializer, PricingTierDataSerializer, TableFieldSerializer, ItemSerializer,
    ItemImageSerializer, ItemDataSerializer, UserExclusivePriceSerializer,
    CartSerializer, CartItemSerializer, OrderSerializer, OrderItemSerializer, CartItemDetailSerializer, OrderItemDetailSerializer, ShippingAddressSerializer, BillingAddressSerializer
)
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank, SearchHeadline
from django.db.models import Q
from decimal import Decimal
from rest_framework.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.db import transaction
from backend_praco.renderers import CustomRenderer

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

class CategoryViewSet(viewsets.ModelViewSet):
    renderer_classes = [CustomRenderer]
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['name']
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = super().get_queryset()
        search_query = self.request.query_params.get('search')
        slug = self.request.query_params.get('slug')
        if search_query:
            qs = qs.filter(
                Q(name__icontains=search_query) |
                Q(slug__icontains=search_query) |
                Q(description__icontains=search_query)
            )
        if slug:
            qs = qs.filter(slug=slug)
        return qs

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [AllowAny()]

class ProductImageViewSet(viewsets.ModelViewSet):
    renderer_classes = [CustomRenderer]
    queryset = ProductImage.objects.all()
    serializer_class = ProductImageSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['product']
    pagination_class = StandardResultsSetPagination

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [AllowAny()]

class ProductViewSet(viewsets.ModelViewSet):
    renderer_classes = [CustomRenderer]
    queryset = Product.objects.all().select_related('category').prefetch_related('images')
    serializer_class = ProductSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['name', 'slug', 'is_new']
    pagination_class = StandardResultsSetPagination

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [AllowAny()]

    def get_queryset(self):
        qs = super().get_queryset()
        category_slug = self.request.query_params.get('category')
        slug = self.request.query_params.get('slug')
        search_query = self.request.query_params.get('search')

        if category_slug:
            try:
                category = Category.objects.get(slug=category_slug)
                qs = qs.filter(category=category)
            except Category.DoesNotExist:
                qs = qs.none()

        if slug:
            qs = qs.filter(slug=slug)

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
                qs = qs.annotate(
                    search=search_vector,
                    rank=search_rank,
                    headline=search_headline
                ).filter(
                    search=search_query_obj
                ).filter(
                    Q(name__icontains=raw_query) | Q(description__icontains=raw_query)
                ).order_by('-rank')

        return qs

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
    renderer_classes = [CustomRenderer]
    queryset = ProductVariant.objects.filter(status="active").select_related('product').prefetch_related('pricing_tiers__pricing_data')
    serializer_class = ProductVariantSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['product', 'name']
    pagination_class = StandardResultsSetPagination

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [AllowAny()]

    @action(detail=True, methods=['get'], url_path='calculate-price')
    def calculate_price(self, request, pk=None):
        pv = self.get_object()
        units = int(request.query_params.get('units', 0))
        price_per = request.query_params.get('price_per', 'pack')

        if units <= 0:
            return Response({"error": "Units must be greater than 0"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            item = pv.items.first()
            if not item:
                return Response({"error": "No items found for this product variant"}, status=status.HTTP_400_BAD_REQUEST)
            units_per_pack = item.units_per_pack or 1
        except Item.DoesNotExist:
            return Response({"error": "No items found for this product variant"}, status=status.HTTP_400_BAD_REQUEST)

        units_per_pallet = units_per_pack  # Assuming pallet logic remains the same
        show_units_per = pv.show_units_per

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

        total = Decimal('0.00')
        if show_units_per in ['pack', 'both'] and price_per == 'pack':
            tiers = pv.pricing_tiers.filter(tier_type='pack').order_by('range_start')
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
            tiers = pv.pricing_tiers.filter(tier_type='pallet').order_by('range_start')
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
            tiers = pv.pricing_tiers.filter(tier_type='pack').order_by('range_start')
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
    renderer_classes = [CustomRenderer]
    queryset = PricingTier.objects.all().select_related('product_variant').prefetch_related('pricing_data')
    serializer_class = PricingTierSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['product_variant', 'tier_type']
    pagination_class = StandardResultsSetPagination

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [AllowAny()]

class PricingTierDataViewSet(viewsets.ModelViewSet):
    renderer_classes = [CustomRenderer]
    queryset = PricingTierData.objects.all().select_related('item__product_variant', 'pricing_tier')
    serializer_class = PricingTierDataSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['item', 'pricing_tier']
    pagination_class = StandardResultsSetPagination

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [AllowAny()]

class TableFieldViewSet(viewsets.ModelViewSet):
    renderer_classes = [CustomRenderer]
    queryset = TableField.objects.all().select_related('product_variant')
    serializer_class = TableFieldSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['product_variant', 'field_type']
    pagination_class = StandardResultsSetPagination

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [AllowAny()]

class ItemImageViewSet(viewsets.ModelViewSet):
    renderer_classes = [CustomRenderer]
    queryset = ItemImage.objects.all()
    serializer_class = ItemImageSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['item']
    pagination_class = StandardResultsSetPagination

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [AllowAny()]

class ItemViewSet(viewsets.ModelViewSet):
    renderer_classes = [CustomRenderer]
    queryset = Item.objects.all().select_related('product_variant__product__category').prefetch_related('data_entries__field', 'images', 'pricing_tier_data')
    serializer_class = ItemSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['product_variant', 'sku', 'status']
    pagination_class = StandardResultsSetPagination

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [AllowAny()]

    def get_queryset(self):
        qs = super().get_queryset()
        width = self.request.query_params.get('width')
        length = self.request.query_params.get('length')
        height = self.request.query_params.get('height')
        measurement_unit = self.request.query_params.get('measurement_unit', '').upper()
        category = self.request.query_params.get('category')
        approx_size = self.request.query_params.get('approx_size', '').lower() == 'true'
        minimum_size = self.request.query_params.get('minimum_size', '').lower() == 'true'

        valid_units = ['MM', 'CM', 'IN', 'M']
        if measurement_unit and measurement_unit not in valid_units:
            return qs.none()

        if category:
            category = category.lower()
            valid_categories = ['box', 'boxes', 'bag', 'bags', 'postal', 'postals']
            if category in valid_categories:
                qs = qs.filter(product_variant__product__category__name__iexact=category)
            else:
                return qs.none()

        if width and length and height:
            try:
                width = Decimal(width)
                length = Decimal(length)
                height = Decimal(height)
            except (ValueError, TypeError):
                return qs.none()

            # Convert dimensions to inches if measurement_unit is not 'IN'
            to_inches = {
                'MM': Decimal('0.0393701'),
                'CM': Decimal('0.393701'),
                'IN': Decimal('1.0'),
                'M': Decimal('39.3701'),
            }
            if measurement_unit and measurement_unit != 'IN':
                width = (width * to_inches[measurement_unit]).quantize(Decimal('0.01'))
                length = (length * to_inches[measurement_unit]).quantize(Decimal('0.01'))
                height = (height * to_inches[measurement_unit]).quantize(Decimal('0.01'))

            # Build dimension filter using height_in_inches, width_in_inches, length_in_inches
            dimension_filter = Q()
            if approx_size:
                # ±5 inch margin for approximate size
                margin = Decimal('5.0')
                width_min = width - margin
                width_max = width + margin
                length_min = length - margin
                length_max = length + margin
                height_min = height - margin
                height_max = height + margin
                dimension_filter = Q(
                    width_in_inches__gte=width_min, width_in_inches__lte=width_max,
                    length_in_inches__gte=length_min, length_in_inches__lte=length_max,
                    height_in_inches__gte=height_min, height_in_inches__lte=height_max
                )
            elif minimum_size:
                # Minimum size: dimensions >= provided values
                dimension_filter = Q(
                    width_in_inches__gte=width,
                    length_in_inches__gte=length,
                    height_in_inches__gte=height
                )
            else:
                # Exact match with ±0.01 inch tolerance
                tolerance = Decimal('0.01')
                dimension_filter = Q(
                    width_in_inches__gte=width - tolerance, width_in_inches__lte=width + tolerance,
                    length_in_inches__gte=length - tolerance, length_in_inches__lte=length + tolerance,
                    height_in_inches__gte=height - tolerance, height_in_inches__lte=height + tolerance
                )

            qs = qs.filter(dimension_filter)

        return qs

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context.update({'request': self.request})
        return context
     
class ItemDataViewSet(viewsets.ModelViewSet):
    renderer_classes = [CustomRenderer]
    queryset = ItemData.objects.all().select_related('item__product_variant', 'field')
    serializer_class = ItemDataSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['item', 'field', 'field__field_type']
    pagination_class = StandardResultsSetPagination

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [AllowAny()]

class UserExclusivePriceViewSet(viewsets.ModelViewSet):
    renderer_classes = [CustomRenderer]
    queryset = UserExclusivePrice.objects.all().select_related('user', 'item__product_variant')
    serializer_class = UserExclusivePriceSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['user', 'item']
    pagination_class = StandardResultsSetPagination

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

class CartViewSet(viewsets.ModelViewSet):
    renderer_classes = [CustomRenderer]
    queryset = Cart.objects.all()
    serializer_class = CartSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def list(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied("Authentication required to access cart.")
        try:
            cart, created = Cart.get_or_create_cart(request.user)
            serializer = self.get_serializer(cart)
            return Response(serializer.data)
        except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            raise PermissionDenied("Authentication required to access cart.")
        return self.queryset.filter(user=self.request.user)

    @action(detail=False, methods=['delete'], url_path='clear')
    def clear_cart(self, request):
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
                    cart.update_pricing_tiers()
                return Response(responses, status=status.HTTP_200_OK)
            else:
                data['cart'] = cart.id
                response = self._process_cart_item(data, cart)
                cart.update_pricing_tiers()
                return Response(response, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def _process_cart_item(self, data, cart):
        item_id = data.get('item')
        pricing_tier_id = data.get('pricing_tier')
        pack_quantity = data.get('pack_quantity', 1)
        unit_type = data.get('unit_type', 'pack')
        user_exclusive_price_id = data.get('user_exclusive_price')

        if not item_id:
            raise ValidationError({"item": "Item ID is required."})

        item = Item.objects.get(id=item_id)
        pricing_tier = PricingTier.objects.get(id=pricing_tier_id)

        existing_cart_item = CartItem.objects.filter(
            cart=cart,
            item=item,
            unit_type=unit_type
        ).first()

        serializer_context = {'request': self.request}
        if existing_cart_item:
            existing_cart_item.pack_quantity = pack_quantity
            existing_cart_item.pricing_tier = pricing_tier
            existing_cart_item.user_exclusive_price = UserExclusivePrice.objects.filter(
                id=user_exclusive_price_id,
                user=cart.user,
                item=item
            ).first() if user_exclusive_price_id else None
            existing_cart_item.full_clean()
            existing_cart_item.save()
            serializer = CartItemDetailSerializer(existing_cart_item, context=serializer_context)
        else:
            cart_item_data = {
                'cart': cart,
                'item': item,
                'pricing_tier': pricing_tier,
                'pack_quantity': pack_quantity,
                'unit_type': unit_type,
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
        try:
            instance = self.get_object()
        except CartItem.DoesNotExist:
            return Response({"detail": "Cart item not found."}, status=status.HTTP_404_NOT_FOUND)

        if instance.item is None:
            instance.delete()
            return Response({"detail": "Cart item has no associated item and has been deleted."}, 
                          status=status.HTTP_410_GONE)

        request_data = request.data.copy()
        if 'item' in request_data:
            del request_data['item']

        serializer = self.get_serializer(instance, data=request_data, partial=True)
        serializer.is_valid(raise_exception=True)
        
        try:
            with transaction.atomic():
                instance = serializer.save()
                instance.cart.update_pricing_tiers()
                response_serializer = CartItemDetailSerializer(instance, context={'request': request})
                return Response(response_serializer.data, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def retrieve(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
        except CartItem.DoesNotExist:
            return Response({"detail": "Cart item not found."}, status=status.HTTP_404_NOT_FOUND)

        if instance.item is None:
            instance.delete()
            return Response({"detail": "Cart item has no associated item and has been deleted."}, 
                          status=status.HTTP_410_GONE)

        serializer = self.get_serializer(instance)
        return Response(serializer.data)

class OrderViewSet(viewsets.ModelViewSet):
    renderer_classes = [CustomRenderer]
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def list(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied("Authentication required to access orders.")
        try:
            queryset = self.get_queryset()
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)
        except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(e)
            return Response({"detail": "An unexpected error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            raise PermissionDenied("Authentication required to access orders.")
        return self.queryset.filter(user=self.request.user).order_by('-created_at')

    def create(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied("Authentication required to create an order.")
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class OrderItemViewSet(viewsets.ModelViewSet):
    renderer_classes = [CustomRenderer]
    queryset = OrderItem.objects.all()
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve']:
            return OrderItemDetailSerializer
        return OrderItemSerializer

    def create(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied("Authentication required to add order items.")
        try:
            data = request.data.copy() if isinstance(request.data, dict) else request.data
            if isinstance(data, list):
                responses = []
                with transaction.atomic():
                    for item_data in data:
                        order_id = item_data.get('order')
                        order = Order.objects.get(id=order_id, user=request.user)
                        item_data['order'] = order.id
                        responses.append(self._process_order_item(item_data, order))
                return Response(responses, status=status.HTTP_200_OK)
            else:
                order_id = data.get('order')
                order = Order.objects.get(id=order_id, user=request.user)
                data['order'] = order.id
                response = self._process_order_item(data, order)
                return Response(response, status=status.HTTP_200_OK)
        except Order.DoesNotExist:
            return Response({"detail": "Order not found or not accessible."}, status=status.HTTP_404_NOT_FOUND)
        except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def _process_order_item(self, data, order):
        item_id = data.get('item')
        pricing_tier_id = data.get('pricing_tier')
        pack_quantity = data.get('pack_quantity', 1)
        user_exclusive_price_id = data.get('user_exclusive_price')

        if not item_id:
            raise ValidationError({"item": "Item ID is required."})

        item = Item.objects.get(id=item_id)
        pricing_tier = PricingTier.objects.get(id=pricing_tier_id)

        existing_order_item = OrderItem.objects.filter(
            order=order,
            item=item,
        ).first()

        serializer_context = {'request': self.request}
        if existing_order_item:
            existing_order_item.pack_quantity = pack_quantity
            existing_order_item.pricing_tier = pricing_tier
            if user_exclusive_price_id:
                existing_order_item.user_exclusive_price = UserExclusivePrice.objects.filter(
                    id=user_exclusive_price_id,
                    user=order.user,
                    item=item
                ).first()
            else:
                existing_order_item.user_exclusive_price = None
            existing_order_item.full_clean()
            existing_order_item.save()
            serializer = OrderItemDetailSerializer(existing_order_item, context=serializer_context)
        else:
            order_item_data = {
                'order': order,
                'item': item,
                'pricing_tier': pricing_tier,
                'pack_quantity': pack_quantity,
                'unit_type': 'pack',
                'user_exclusive_price': UserExclusivePrice.objects.filter(
                    id=user_exclusive_price_id,
                    user=order.user,
                    item=item
                ).first() if user_exclusive_price_id else None
            }
            order_item = OrderItem(**order_item_data)
            order_item.full_clean()
            order_item.save()
            serializer = OrderItemDetailSerializer(order_item, context=serializer_context)

        return serializer.data

    def update(self, request, *args, **kwargs):
        pk = kwargs.get('pk')
        try:
            instance = self.get_queryset().get(pk=pk)
        except OrderItem.DoesNotExist:
            return Response({"detail": "Order item not found."}, status=status.HTTP_404_NOT_FOUND)

        if instance.item is None:
            instance.delete()
            return Response({"detail": "Order item has no associated item and has been deleted."}, status=status.HTTP_410_GONE)

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

        response_serializer = OrderItemDetailSerializer(instance, context={'request': request})
        return Response(response_serializer.data, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
        except OrderItem.DoesNotExist:
            return Response({"detail": "Order item not found."}, status=status.HTTP_404_NOT_FOUND)

        if instance.item is None:
            instance.delete()
            return Response({"detail": "Order item has no associated item and has been deleted."}, status=status.HTTP_410_GONE)

        serializer = self.get_serializer(instance)
        return Response(serializer.data)

class AddressViewSet(viewsets.ModelViewSet):
    renderer_classes = [CustomRenderer]
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        model = self.serializer_class.Meta.model
        return model.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class ShippingAddressViewSet(AddressViewSet):
    renderer_classes = [CustomRenderer]
    serializer_class = ShippingAddressSerializer
    queryset = ShippingAddress.objects.all()
    pagination_class = StandardResultsSetPagination

class BillingAddressViewSet(AddressViewSet):
    renderer_classes = [CustomRenderer]
    serializer_class = BillingAddressSerializer
    queryset = BillingAddress.objects.all()
    pagination_class = StandardResultsSetPagination