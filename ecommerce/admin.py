from django.contrib import admin
from django import forms
from .models import (
    Category, Product, ProductImage, ProductVariant, PricingTier, PricingTierData,
    TableField, Item, ItemImage, ItemData, UserExclusivePrice, Cart, CartItem, Order, OrderItem
)
from decimal import Decimal

class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'created_at')
    search_fields = ('name', 'slug')
    list_filter = ('created_at',)
    ordering = ('name',)
    fields = ('name', 'slug', 'description', 'image', 'slider_image')
    prepopulated_fields = {'slug': ('name',)}

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
    list_display = ('name', 'slug', 'category', 'is_new', 'created_at')
    search_fields = ('name', 'category__name')
    list_filter = ('category', 'is_new', 'created_at')
    ordering = ('name',)
    inlines = [ProductImageInline]
    prepopulated_fields = {'slug': ('name',)}

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class PricingTierForm(forms.ModelForm):
    class Meta:
        model = PricingTier
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        range_start = cleaned_data.get('range_start')
        range_end = cleaned_data.get('range_end')
        no_end_range = cleaned_data.get('no_end_range')
        tier_type = cleaned_data.get('tier_type')
        product_variant = cleaned_data.get('product_variant')

        if range_start is None:
            raise forms.ValidationError("Range start is required and must be a positive integer.")
        if range_start <= 0:
            raise forms.ValidationError("Range start must be greater than 0.")
        if no_end_range:
            if range_end is not None:
                raise forms.ValidationError("Range end must be blank when 'No End Range' is checked.")
        else:
            if range_end is None:
                raise forms.ValidationError("Range end is required when 'No End Range' is not checked.")
            if range_end < range_start:
                raise forms.ValidationError("Range end must be greater than or equal to range start.")

        # Check for pack tier requirement for pallet tiers
        if tier_type == 'pallet' and product_variant and product_variant.show_units_per != 'pallet':
            existing_pack_tiers = PricingTier.objects.filter(
                product_variant=product_variant,
                tier_type='pack'
            ).exclude(id=self.instance.id)
            if not existing_pack_tiers.exists():
                raise forms.ValidationError(
                    "You must create at least one 'pack' pricing tier before adding a 'pallet' pricing tier, "
                    "unless 'Show Units Per' is set to 'Pallet Only'."
                )

        return cleaned_data

class PricingTierInline(admin.TabularInline):
    model = PricingTier
    extra = 1
    form = PricingTierForm

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class PricingTierAdmin(admin.ModelAdmin):
    list_display = ('product_variant', 'tier_type', 'range_start', 'range_end', 'no_end_range', 'created_at')
    search_fields = ('product_variant__name', 'tier_type')
    list_filter = ('tier_type', 'no_end_range', 'created_at')
    ordering = ('product_variant', 'tier_type', 'range_start')
    form = PricingTierForm
    autocomplete_fields = ['product_variant']

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

        tier_types = []
        valid_tiers = []
        total_forms = int(self.data.get('pricing_tiers-TOTAL_FORMS', 0))
        for i in range(total_forms):
            if f'pricing_tiers-{i}-DELETE' in self.data and self.data[f'pricing_tiers-{i}-DELETE'] == 'on':
                continue
            tier_type = self.data.get(f'pricing_tiers-{i}-tier_type')
            range_start = self.data.get(f'pricing_tiers-{i}-range_start')
            range_end = self.data.get(f'pricing_tiers-{i}-range_end')
            no_end_range = self.data.get(f'pricing_tiers-{i}-no_end_range') == 'on'

            if not tier_type or not range_start:
                continue

            try:
                range_start = int(range_start)
                if range_start <= 0:
                    raise ValueError
            except (ValueError, TypeError):
                raise forms.ValidationError(
                    f"Pricing tier {i+1}: Range start must be a positive integer."
                )

            if not no_end_range and range_end:
                try:
                    range_end = int(range_end)
                    if range_end < range_start:
                        raise forms.ValidationError(
                            f"Pricing tier {i+1}: Range end must be greater than or equal to range start."
                        )
                except (ValueError, TypeError):
                    raise forms.ValidationError(
                        f"Pricing tier {i+1}: Range end must be a valid integer."
                    )
            elif not no_end_range and not range_end:
                raise forms.ValidationError(
                    f"Pricing tier {i+1}: Range end is required when 'No End Range' is not checked."
                )
            elif no_end_range and range_end:
                raise forms.ValidationError(
                    f"Pricing tier {i+1}: Range end must be blank when 'No End Range' is checked."
                )

            tier_types.append(tier_type)
            valid_tiers.append({
                'tier_type': tier_type,
                'range_start': range_start,
                'range_end': None if no_end_range else range_end,
                'no_end_range': no_end_range
            })

        if not valid_tiers:
            raise forms.ValidationError("At least one valid Pricing Tier is required for a Product Variant.")

        pack_tiers = [tier for tier in valid_tiers if tier['tier_type'] == 'pack']
        pallet_tiers = [tier for tier in valid_tiers if tier['tier_type'] == 'pallet']

        if show_units_per == 'pack':
            if not pack_tiers:
                raise forms.ValidationError("At least one 'pack' Pricing Tier is required when show_units_per is 'pack'.")
            if pallet_tiers:
                raise forms.ValidationError("Pallet Pricing Tiers are not allowed when show_units_per is 'pack'.")
            pack_no_end = [tier for tier in pack_tiers if tier['no_end_range']]
            if len(pack_no_end) != 1:
                raise forms.ValidationError("Exactly one 'pack' Pricing Tier must have 'No End Range' checked when show_units_per is 'pack'.")
        elif show_units_per == 'pallet':
            if not pallet_tiers:
                raise forms.ValidationError("At least one 'pallet' Pricing Tier is required when show_units_per is 'pallet'.")
            if pack_tiers:
                raise forms.ValidationError("Pack Pricing Tiers are not allowed when show_units_per is 'pallet'.")
            pallet_no_end = [tier for tier in pallet_tiers if tier['no_end_range']]
            if len(pallet_no_end) != 1:
                raise forms.ValidationError("Exactly one 'pallet' Pricing Tier must have 'No End Range' checked when show_units_per is 'pallet'.")
        elif show_units_per == 'both':
            if not pack_tiers or not pallet_tiers:
                raise forms.ValidationError("At least one 'pack' and one 'pallet' Pricing Tier are required when show_units_per is 'both'.")
            pack_no_end = [tier for tier in pack_tiers if tier['no_end_range']]
            pallet_no_end = [tier for tier in pallet_tiers if tier['no_end_range']]
            if len(pack_no_end) != 1 or len(pallet_no_end) != 1:
                raise forms.ValidationError("Exactly one 'pack' and one 'pallet' Pricing Tier must have 'No End Range' checked when show_units_per is 'both'.")

        return cleaned_data

class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ('name', 'product', 'units_per_pack', 'units_per_pallet', 'show_units_per', 'created_at')
    search_fields = ('name', 'product__name')
    list_filter = ('product', 'show_units_per', 'created_at')
    ordering = ('name',)
    inlines = [PricingTierInline, TableFieldInline]
    form = ProductVariantForm
    search_fields = ['name', 'product__name']

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        obj = form.instance
        obj.validate_pricing_tiers()

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class PricingTierDataInline(admin.TabularInline):
    model = PricingTierData
    extra = 1

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'pricing_tier':
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
    list_display = (
        'sku', 'product_variant', 'is_physical_product', 'status',
        'height', 'width', 'length', 'measurement_unit', 'created_at'
    )
    search_fields = ('sku', 'product_variant__name')
    list_filter = (
        'product_variant', 'is_physical_product', 'status', 'measurement_unit', 'created_at'
    )
    ordering = ('sku',)
    inlines = [PricingTierDataInline, ItemImageInline, ItemDataInline]
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
    autocomplete_fields = ['user', 'item']

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 1
    autocomplete_fields = ['item', 'pricing_tier', 'user_exclusive_price']
    readonly_fields = ('unit_price', 'user_exclusive_price', 'subtotal')

    def subtotal(self, obj):
        return obj.subtotal() if obj.pk else Decimal('0.00')
    subtotal.short_description = 'Subtotal'

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class CartAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at', 'calculate_total')
    search_fields = ('user__email',)
    list_filter = ('created_at',)
    ordering = ('user',)
    inlines = [CartItemInline]
    readonly_fields = ('created_at', 'calculate_total')
    autocomplete_fields = ['user']

    def calculate_total(self, obj):
        return obj.calculate_total()
    calculate_total.short_description = 'Total'

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 1
    autocomplete_fields = ['item', 'pricing_tier', 'user_exclusive_price']
    readonly_fields = ('unit_price', 'user_exclusive_price', 'subtotal')

    def subtotal(self, obj):
        return obj.subtotal() if obj.pk else Decimal('0.00')
    subtotal.short_description = 'Subtotal'

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'user', 'status', 'total_amount', 'payment_status',
        'payment_method', 'created_at'
    )
    search_fields = ('user__email', 'transaction_id')
    list_filter = ('status', 'payment_status', 'payment_method', 'created_at')
    ordering = ('-created_at',)
    inlines = [OrderItemInline]
    readonly_fields = ('created_at', 'total_amount')
    autocomplete_fields = ['user']
    list_editable = ('status', 'payment_status', 'payment_method')

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        form.instance.calculate_total()

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

admin.site.register(Category, CategoryAdmin)
admin.site.register(Product, ProductAdmin)
admin.site.register(ProductVariant, ProductVariantAdmin)
admin.site.register(PricingTier, PricingTierAdmin)
admin.site.register(Item, ItemAdmin)
admin.site.register(UserExclusivePrice, UserExclusivePriceAdmin)
admin.site.register(Cart, CartAdmin)
admin.site.register(Order, OrderAdmin)