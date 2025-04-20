from django.urls import path, include
from rest_framework.routers import DefaultRouter
from ecommerce.views import (
    CategoryViewSet, ProductViewSet, ProductImageViewSet, ProductVariantViewSet,
    PricingTierViewSet, PricingTierDataViewSet, TableFieldViewSet, ItemViewSet, ItemImageViewSet,
    ItemDataViewSet, UserExclusivePriceViewSet
)

router = DefaultRouter()
router.register(r'categories', CategoryViewSet)
router.register(r'products', ProductViewSet)
router.register(r'product-images', ProductImageViewSet)
router.register(r'product-variants', ProductVariantViewSet)
router.register(r'pricing-tiers', PricingTierViewSet)
router.register(r'pricing-tier-data', PricingTierDataViewSet)
router.register(r'table-fields', TableFieldViewSet)
router.register(r'items', ItemViewSet)
router.register(r'item-images', ItemImageViewSet)
router.register(r'item-data', ItemDataViewSet)
router.register(r'user-exclusive-prices', UserExclusivePriceViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('ckeditor/', include('ckeditor_uploader.urls')),
]
 

# search / adavance search
# cart
# navbar
# excusive pricing
# ui fixes
# test apis


# tracking
# checkout
# email sending