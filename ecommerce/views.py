from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import action
from ecommerce.models import Category, Product, ProductImage, ProductVariant, PricingTier, PricingTierData, TableField, Item, ItemImage, ItemData, UserExclusivePrice
from ecommerce.serializers import (
    CategorySerializer, ProductImageSerializer, ProductSerializer, ProductVariantSerializer,
    PricingTierSerializer, PricingTierDataSerializer, TableFieldSerializer, ItemSerializer, ItemImageSerializer,
    ItemDataSerializer, UserExclusivePriceSerializer
)

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['name']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

class ProductImageViewSet(viewsets.ModelViewSet):
    queryset = ProductImage.objects.all()
    serializer_class = ProductImageSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['product']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all().select_related('category').prefetch_related('images')
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['category', 'name', 'is_new']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

class ProductVariantViewSet(viewsets.ModelViewSet):
    queryset = ProductVariant.objects.all().select_related('product').prefetch_related('pricing_tiers__pricing_data')
    serializer_class = ProductVariantSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['product', 'name']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

    @action(detail=True, methods=['get'], url_path='calculate-price')
    def calculate_price(self, request, pk=None):
        product_variant = self.get_object()
        units = int(request.query_params.get('units', 0))
        price_per = request.query_params.get('price_per', 'pack')

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

        total = 0
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
        elif show_units_per in ['pallet', 'both'] and price_per == 'pack' and pallets > 0:
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
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['product_variant', 'tier_type']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

class PricingTierDataViewSet(viewsets.ModelViewSet):
    queryset = PricingTierData.objects.all().select_related('item__product_variant', 'pricing_tier')
    serializer_class = PricingTierDataSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['item', 'pricing_tier']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

class TableFieldViewSet(viewsets.ModelViewSet):
    queryset = TableField.objects.all().select_related('product_variant')
    serializer_class = TableFieldSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['product_variant', 'field_type']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

class ItemImageViewSet(viewsets.ModelViewSet):
    queryset = ItemImage.objects.all()
    serializer_class = ItemImageSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['item']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

class ItemViewSet(viewsets.ModelViewSet):
    queryset = Item.objects.all().select_related('product_variant__product').prefetch_related('data_entries__field', 'images', 'pricing_tier_data')
    serializer_class = ItemSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['product_variant', 'sku', 'status']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context.update({'request': self.request})
        return context

class ItemDataViewSet(viewsets.ModelViewSet):
    queryset = ItemData.objects.all().select_related('item__product_variant', 'field')
    serializer_class = ItemDataSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['item', 'field', 'field__field_type']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

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