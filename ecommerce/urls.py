from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CategoryViewSet, CategoryImageViewSet, ProductViewSet, SubCategoryViewSet,
    TableFieldViewSet, ProductVariantViewSet, ProductVariantDataViewSet, UserExclusivePriceViewSet
)

router = DefaultRouter()
router.register(r'categories', CategoryViewSet)
router.register(r'category-images', CategoryImageViewSet)
router.register(r'products', ProductViewSet)
router.register(r'subcategories', SubCategoryViewSet)
router.register(r'table-fields', TableFieldViewSet)
router.register(r'product-variants', ProductVariantViewSet)
router.register(r'product-variant-data', ProductVariantDataViewSet)
router.register(r'user-exclusive-prices', UserExclusivePriceViewSet)

urlpatterns = [
    path('', include(router.urls)),
]