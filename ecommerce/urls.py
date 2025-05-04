from django.urls import path, include
from rest_framework.routers import DefaultRouter
from ecommerce.views import (
    CategoryViewSet, ProductViewSet, ProductImageViewSet, ProductVariantViewSet,
    PricingTierViewSet, PricingTierDataViewSet, TableFieldViewSet, ItemViewSet,
    ItemImageViewSet, ItemDataViewSet, UserExclusivePriceViewSet,
    CartViewSet, CartItemViewSet, OrderViewSet, OrderItemViewSet
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
router.register(r'carts', CartViewSet)
router.register(r'cart-items', CartItemViewSet)
router.register(r'orders', OrderViewSet)
router.register(r'order-items', OrderItemViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path("ckeditor5/", include('django_ckeditor_5.urls')),
]
 
# product details
# cart
# checkout
# search / adavance search
# ui fixes
    # navigation styling
    # loading animation
# exclusive pricing # ALAHAMDULILLAH done

# ui fixes
# test apis

# email sending
# tracking