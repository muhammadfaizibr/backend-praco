from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CategoryViewSet, ProductImageViewSet, ProductViewSet, ProductVariantViewSet,
    TableFieldViewSet, ItemImageViewSet, ItemViewSet, ItemDataViewSet, UserExclusivePriceViewSet
)

router = DefaultRouter()
router.register(r'categories', CategoryViewSet)
router.register(r'product-images', ProductImageViewSet)
router.register(r'products', ProductViewSet)
router.register(r'product-variants', ProductVariantViewSet)
router.register(r'table-fields', TableFieldViewSet)
router.register(r'item-images', ItemImageViewSet)
router.register(r'items', ItemViewSet)
router.register(r'item-data', ItemDataViewSet)
router.register(r'user-exclusive-prices', UserExclusivePriceViewSet)

urlpatterns = [
    path('', include(router.urls)),
]