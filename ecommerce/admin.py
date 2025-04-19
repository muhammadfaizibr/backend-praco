from django.contrib import admin
from django import forms
from django.core.exceptions import ValidationError
from .models import Category, Product, ProductImage, ProductVariant, PricingTier, PricingTierData, TableField, Item, ItemImage, ItemData, UserExclusivePrice

class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')
    search_fields = ('name',)
    list_filter = ('created_at',)
    ordering = ('name',)

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'is_new', 'created_at')
    search_fields = ('name', 'category__name')
    list_filter = ('category', 'is_new', 'created_at')
    ordering = ('name',)
    inlines = [ProductImageInline]

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class PricingTierInline(admin.TabularInline):
    model = PricingTier
    extra = 1

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class TableFieldInline(admin.TabularInline):
    model = TableField
    extra = 1

    def has_change_permission(self, request, obj=None):
        if obj and obj.name in TableField.RESERVED_NAMES:
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj and obj.name in TableField.RESERVED_NAMES:
            return False
        return super().has_delete_permission(request, obj)

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class ProductVariantForm(forms.ModelForm):
    class Meta:
        model = ProductVariant
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        show_units_per = cleaned_data.get('show_units_per')

        # Access the PricingTier inline formset data from self.data
        tier_types = []
        total_forms = int(self.data.get('pricing_tiers-TOTAL_FORMS', 0))
        for i in range(total_forms):
            if f'pricing_tiers-{i}-DELETE' in self.data:
                continue
            tier_type = self.data.get(f'pricing_tiers-{i}-tier_type')
            if tier_type:
                tier_types.append(tier_type)

        # Validate PricingTiers
        if not tier_types:
            raise forms.ValidationError("At least one Pricing Tier is required for a Product Variant.")

        pack_tiers = 'pack' in tier_types
        pallet_tiers = 'pallet' in tier_types

        if show_units_per == 'pack':
            if not pack_tiers:
                raise forms.ValidationError("A 'pack' Pricing Tier is required when show_units_per is 'pack'.")
            if pallet_tiers:
                raise forms.ValidationError("A 'pallet' Pricing Tier is not allowed when show_units_per is 'pack'.")
        elif show_units_per == 'pallet':
            if not pallet_tiers:
                raise forms.ValidationError("A 'pallet' Pricing Tier is required when show_units_per is 'pallet'.")
            if pack_tiers:
                raise forms.ValidationError("A 'pack' Pricing Tier is not allowed when show_units_per is 'pallet'.")
        elif show_units_per == 'both':
            errors = []
            if not pack_tiers:
                errors.append("A 'pack' Pricing Tier is required when show_units_per is 'both'.")
            if not pallet_tiers:
                errors.append("A 'pallet' Pricing Tier is required when show_units_per is 'both'.")
            if errors:
                raise forms.ValidationError(errors)

        return cleaned_data

class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ('name', 'product', 'units_per_pack', 'units_per_pallet', 'show_units_per', 'created_at')
    search_fields = ('name', 'product__name')
    list_filter = ('product', 'show_units_per', 'created_at')
    ordering = ('name',)
    inlines = [PricingTierInline, TableFieldInline]
    form = ProductVariantForm

    # Enable autocomplete search for ProductVariant
    search_fields = ['name', 'product__name']  # Fields to search in autocomplete

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class PricingTierDataInline(admin.TabularInline):
    model = PricingTierData
    extra = 1

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # Filter pricing_tier based on the selected product_variant
        if db_field.name == 'pricing_tier':
            # Get the Item instance being edited (if editing an existing Item)
            item_id = request.resolver_match.kwargs.get('object_id')
            if item_id:
                item = Item.objects.get(pk=item_id)
                product_variant = item.product_variant
                kwargs['queryset'] = PricingTier.objects.filter(product_variant=product_variant)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }
        js = ('admin/js/filter_pricing_tier.js',)

class ItemImageInline(admin.TabularInline):
    model = ItemImage
    extra = 1

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class ItemDataInline(admin.TabularInline):
    model = ItemData
    extra = 1

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # Filter field based on the selected product_variant
        if db_field.name == 'field':
            item_id = request.resolver_match.kwargs.get('object_id')
            if item_id:
                item = Item.objects.get(pk=item_id)
                product_variant = item.product_variant
                kwargs['queryset'] = TableField.objects.filter(product_variant=product_variant)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }
        js = ('admin/js/filter_item_data.js',)

class ItemAdmin(admin.ModelAdmin):
    list_display = ('sku', 'product_variant', 'is_physical_product', 'status', 'created_at')
    search_fields = ('sku', 'product_variant__name')
    list_filter = ('product_variant', 'is_physical_product', 'status', 'created_at')
    ordering = ('sku',)
    inlines = [PricingTierDataInline, ItemImageInline, ItemDataInline]

    # Enable autocomplete for product_variant
    autocomplete_fields = ['product_variant']

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }
        js = ('admin/js/filter_pricing_tier.js', 'admin/js/filter_item_data.js',)

class UserExclusivePriceAdmin(admin.ModelAdmin):
    list_display = ('user', 'item', 'discount_percentage', 'created_at')
    search_fields = ('user__email', 'item__sku')
    list_filter = ('created_at',)
    ordering = ('user',)

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

admin.site.register(Category, CategoryAdmin)
admin.site.register(Product, ProductAdmin)
admin.site.register(ProductVariant, ProductVariantAdmin)
admin.site.register(Item, ItemAdmin)
admin.site.register(UserExclusivePrice, UserExclusivePriceAdmin)