from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from .models import Category, CategoryImage, Product, SubCategory, TableField, ProductVariant, ProductVariantData, UserExclusivePrice
from .serializers import (
    CategorySerializer, CategoryImageSerializer, ProductSerializer, SubCategorySerializer,
    TableFieldSerializer, ProductVariantSerializer, ProductVariantDataSerializer, UserExclusivePriceSerializer
)

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all().prefetch_related('images')
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

class CategoryImageViewSet(viewsets.ModelViewSet):
    queryset = CategoryImage.objects.all()
    serializer_class = CategoryImageSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all().select_related('category')
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

class SubCategoryViewSet(viewsets.ModelViewSet):
    queryset = SubCategory.objects.all().select_related('product').prefetch_related('table_fields')
    serializer_class = SubCategorySerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

class TableFieldViewSet(viewsets.ModelViewSet):
    queryset = TableField.objects.all().select_related('subcategory')
    serializer_class = TableFieldSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

class ProductVariantViewSet(viewsets.ModelViewSet):
    queryset = ProductVariant.objects.all().select_related('subcategory__product').prefetch_related('data_entries__field')
    serializer_class = ProductVariantSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

class ProductVariantDataViewSet(viewsets.ModelViewSet):
    queryset = ProductVariantData.objects.all().select_related('variant__subcategory', 'field')
    serializer_class = ProductVariantDataSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

class UserExclusivePriceViewSet(viewsets.ModelViewSet):
    queryset = UserExclusivePrice.objects.all().select_related('user', 'product')
    serializer_class = UserExclusivePriceSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]