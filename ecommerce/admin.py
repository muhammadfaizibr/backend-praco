from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from .models import (
    Category, Product, ProductImage, ProductVariant, PricingTier, PricingTierData,
    TableField, Item, ItemImage, ItemData, UserExclusivePrice, Cart, CartItem, Order, OrderItem
)

class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'created_at')
    search_fields = ('name', 'slug')
    list_filter = ('created_at',)
    ordering = ('name',)
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('created_at',)

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug'),
            'description': 'Core details for the category.'
        }),
        ('Details', {
            'fields': ('description', 'image', 'slider_image'),
            'description': 'Additional category information and images.'
        }),
        ('Metadata', {
            'fields': (),
            'classes': ('collapse',),
            'description': 'Timestamps and other metadata.'
        }),
    )

    def save_model(self, request, obj, form, change):
        try:
            obj.save()
        except ValidationError as e:
            for field, errors in e.error_dict.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}" if field != '__all__' else error)
            raise

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ('image', 'created_at')
    readonly_fields = ('created_at',)

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
    autocomplete_fields = ['category']
    readonly_fields = ('created_at',)

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'category'),
            'description': 'Core product details.'
        }),
        ('Details', {
            'fields': ('description', 'is_new'),
            'description': 'Additional product information.'
        }),
        ('Metadata', {
            'fields': (),
            'classes': ('collapse',),
            'description': 'Timestamps and other metadata.'
        }),
    )

    def save_model(self, request, obj, form, change):
        try:
            obj.save()
        except ValidationError as e:
            for field, errors in e.error_dict.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}" if field != '__all__' else error)
            raise

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class PricingTierInline(admin.TabularInline):
    model = PricingTier
    extra = 1
    fields = ('tier_type', 'range_start', 'range_end', 'no_end_range')
    autocomplete_fields = ['product_variant']

    def get_formset(self, request, obj=None, **kwargs):
        if obj is None or not obj.pk:
            kwargs['form'] = forms.ModelForm
        return super().get_formset(request, obj, **kwargs)

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class PricingTierAdmin(admin.ModelAdmin):
    list_display = ('product_variant', 'tier_type', 'range_start', 'range_end', 'no_end_range', 'created_at')
    search_fields = ('product_variant__name', 'tier_type')
    list_filter = ('tier_type', 'no_end_range', 'created_at')
    ordering = ('product_variant', 'tier_type', 'range_start')
    autocomplete_fields = ['product_variant']
    readonly_fields = ('created_at',)

    fieldsets = (
        ('Basic Information', {
            'fields': ('product_variant', 'tier_type'),
            'description': 'Core pricing tier details.'
        }),
        ('Range Details', {
            'fields': ('range_start', 'range_end', 'no_end_range'),
            'classes': ('inline-group',),
            'description': 'Specify the quantity range for this tier.'
        }),
        ('Metadata', {
            'fields': (),
            'classes': ('collapse',),
            'description': 'Timestamps and other metadata.'
        }),
    )

    def save_model(self, request, obj, form, change):
        try:
            obj.save()
        except ValidationError as e:
            for field, errors in e.error_dict.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}" if field != '__all__' else error)
            raise

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class ProductVariantForm(forms.ModelForm):
    class Meta:
        model = ProductVariant
        exclude = ('created_at', 'status')

class TableFieldForm(forms.ModelForm):
    class Meta:
        model = TableField
        fields = '__all__'

    def clean_name(self):
        name = self.cleaned_data.get('name')
        if name and name.lower() in TableField.RESERVED_NAMES:
            raise ValidationError(f"The name '{name}' is reserved and cannot be used.")
        return name

    def clean_field_type(self):
        field_type = self.cleaned_data.get('field_type')
        valid_types = [choice[0] for choice in TableField.FIELD_TYPES]
        if field_type and field_type not in valid_types:
            raise ValidationError(f"Field type must be one of: {', '.join(valid_types)}.")
        return field_type

class TableFieldInline(admin.TabularInline):
    model = TableField
    extra = 1
    form = TableFieldForm
    fields = ('name', 'field_type', 'long_field')
    autocomplete_fields = ['product_variant']

    def get_formset(self, request, obj=None, **kwargs):
        if obj is None or not obj.pk:
            kwargs['form'] = forms.ModelForm
        return super().get_formset(request, obj, **kwargs)

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
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ('name', 'product', 'status', 'show_units_per', 'units_per_pack', 'units_per_pallet', 'created_at')
    search_fields = ('name', 'product__name')
    list_filter = ('status', 'show_units_per', 'created_at')
    ordering = ('product', 'name')
    inlines = [PricingTierInline, TableFieldInline]
    form = ProductVariantForm
    autocomplete_fields = ['product']
    readonly_fields = ('status', 'created_at')

    fieldsets = (
        ('Basic Information', {
            'fields': ('product', 'name'),
            'description': 'Core variant details.'
        }),
        ('Unit Details', {
            'fields': ('show_units_per', 'units_per_pack', 'units_per_pallet'),
            'classes': ('inline-group',),
            'description': 'Specify unit configuration for packs and pallets.'
        }),
        ('Metadata', {
            'fields': (),
            'classes': ('collapse',),
            'description': 'Timestamps and other metadata.'
        }),
    )

    def get_inlines(self, request, obj):
        if obj is None or not obj.pk:
            return []
        return [PricingTierInline, TableFieldInline]

    def save_model(self, request, obj, form, change):
        try:
            obj.save()
        except ValidationError as e:
            for field, errors in e.error_dict.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}" if field != '__all__' else error)
            raise

    def save_related(self, request, form, formsets, change):
        try:
            super().save_related(request, form, formsets, change)
        except ValidationError as e:
            for field, errors in e.error_dict.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}" if field != '__all__' else error)
            raise

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }
        js = ('admin/js/product_variant_admin.js',)

class PricingTierDataAdmin(admin.ModelAdmin):
    list_display = ('item', 'pricing_tier', 'price', 'created_at')
    search_fields = ('item__sku', 'pricing_tier__product_variant__name')
    list_filter = ('created_at',)
    ordering = ('item', 'pricing_tier')
    autocomplete_fields = ['item', 'pricing_tier']
    readonly_fields = ('created_at',)

    fieldsets = (
        ('Basic Information', {
            'fields': ('item', 'pricing_tier', 'price'),
            'description': 'Pricing data details.'
        }),
        ('Metadata', {
            'fields': (),
            'classes': ('collapse',),
            'description': 'Timestamps and other metadata.'
        }),
    )

    def save_model(self, request, obj, form, change):
        try:
            obj.save()
        except ValidationError as e:
            for field, errors in e.error_dict.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}" if field != '__all__' else error)
            raise

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class TableFieldAdmin(admin.ModelAdmin):
    list_display = ('name', 'product_variant', 'field_type', 'long_field', 'created_at')
    search_fields = ('name', 'product_variant__name')
    list_filter = ('field_type', 'long_field', 'created_at')
    ordering = ('product_variant', 'name')
    form = TableFieldForm
    autocomplete_fields = ['product_variant']
    readonly_fields = ('created_at',)

    fieldsets = (
        ('Basic Information', {
            'fields': ('product_variant', 'name'),
            'description': 'Core table field details.'
        }),
        ('Field Details', {
            'fields': ('field_type', 'long_field'),
            'classes': ('inline-group',),
            'description': 'Specify field type and display options.'
        }),
        ('Metadata', {
            'fields': (),
            'classes': ('collapse',),
            'description': 'Timestamps and other metadata.'
        }),
    )

    def save_model(self, request, obj, form, change):
        try:
            obj.save()
        except ValidationError as e:
            for field, errors in e.error_dict.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}" if field != '__all__' else error)
            raise

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }
class ItemForm(forms.ModelForm):
    class Meta:
        model = Item
        fields = [
            'product_variant', 'title', 'sku', 'is_physical_product',
            'weight', 'weight_unit', 'track_inventory', 'stock',
            'height', 'width', 'length', 'measurement_unit'
        ]
        exclude = ('status', 'created_at')

    def clean(self):
        cleaned_data = super().clean()
        product_variant = cleaned_data.get('product_variant')
        if not product_variant:
            raise ValidationError({
                'product_variant': ["Please select a product variant for the item."]
            })
        if self.instance.pk:
            cleaned_data['status'] = self.instance.status
        else:
            cleaned_data['status'] = 'draft'
        return cleaned_data
    
class PricingTierDataInline(admin.TabularInline):
    model = PricingTierData
    extra = 1
    fields = ('pricing_tier', 'price')
    autocomplete_fields = ['pricing_tier']

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class ItemImageInline(admin.TabularInline):
    model = ItemImage
    extra = 1
    fields = ('image', 'created_at')
    readonly_fields = ('created_at',)

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class ItemDataInline(admin.TabularInline):
    model = ItemData
    extra = 1
    fields = ('field', 'value_text', 'value_number', 'value_image')
    autocomplete_fields = ['field']

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }


class ItemAdmin(admin.ModelAdmin):
    list_display = ('sku', 'product_variant', 'status', 'is_physical_product', 'track_inventory', 'stock', 'created_at')
    search_fields = ('sku', 'product_variant__name')
    list_filter = ('status', 'is_physical_product', 'track_inventory', 'created_at')
    ordering = ('sku', 'product_variant')
    form = ItemForm
    autocomplete_fields = ['product_variant']
    readonly_fields = ('status', 'created_at', 'height_in_inches', 'width_in_inches', 'length_in_inches')

    fieldsets = (
        ('Basic Information', {
            'fields': ('product_variant', 'title', 'sku'),
            'description': 'Core item details.'
        }),
        ('Physical Product Details', {
            'fields': ('is_physical_product', 'weight', 'weight_unit'),
            'classes': ('inline-group',),
            'description': 'Specify details for physical products.'
        }),
        ('Inventory Management', {
            'fields': ('track_inventory', 'stock'),
            'classes': ('inline-group',),
            'description': 'Configure inventory tracking options.'
        }),
        ('Dimensions', {
            'fields': ('height', 'width', 'length', 'measurement_unit', 'height_in_inches', 'width_in_inches', 'length_in_inches'),
            'classes': ('inline-group',),
            'description': 'Required for categories like Box, Postal, or Bag. Dimensions in inches are calculated automatically.'
        }),
        ('Metadata', {
            'fields': (),
            'classes': ('collapse',),
            'description': 'Timestamps and other metadata.'
        }),
    )

    def get_inlines(self, request, obj):
        if obj is None or not obj.pk:
            return []
        return [PricingTierDataInline, ItemImageInline, ItemDataInline]

    def save_model(self, request, obj, form, change):
        try:
            if not form.is_valid():
                return  # Form validation will handle errors
            obj.save()
        except ValidationError as e:
            for field, errors in e.error_dict.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}" if field != '__all__' else error)
            raise

    def save_related(self, request, form, formsets, change):
        try:
            if not form.is_valid():
                return  # Ensure form is valid before saving related
            super().save_related(request, form, formsets, change)
            obj = form.instance
            pricing_tiers = obj.product_variant.pricing_tiers.all()
            existing_pricing_data = set(obj.pricing_tier_data.values_list('pricing_tier_id', flat=True))
            if all(tier.id in existing_pricing_data for tier in pricing_tiers):
                obj.status = 'active'
            else:
                obj.status = 'draft'
            obj.save()
        except ValidationError as e:
            for field, errors in e.error_dict.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}" if field != '__all__' else error)
            raise

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class ItemImageAdmin(admin.ModelAdmin):
    list_display = ('item', 'image', 'created_at')
    search_fields = ('item__sku',)
    list_filter = ('created_at',)
    ordering = ('item', 'created_at')
    autocomplete_fields = ['item']
    readonly_fields = ('created_at',)

    fieldsets = (
        ('Basic Information', {
            'fields': ('item', 'image'),
            'description': 'Core image details.'
        }),
        ('Metadata', {
            'fields': (),
            'classes': ('collapse',),
            'description': 'Timestamps and other metadata.'
        }),
    )

    def save_model(self, request, obj, form, change):
        try:
            obj.save()
        except ValidationError as e:
            for field, errors in e.error_dict.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}" if field != '__all__' else error)
            raise

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class ItemDataAdmin(admin.ModelAdmin):
    list_display = ('item', 'field', 'value_text', 'value_number', 'value_image', 'created_at')
    search_fields = ('item__sku', 'field__name')
    list_filter = ('field__field_type', 'created_at')
    ordering = ('item', 'field')
    autocomplete_fields = ['item', 'field']
    readonly_fields = ('created_at',)

    fieldsets = (
        ('Basic Information', {
            'fields': ('item', 'field'),
            'description': 'Core data details.'
        }),
        ('Values', {
            'fields': ('value_text', 'value_number', 'value_image'),
            'classes': ('inline-group',),
            'description': 'Specify the value based on the field type.'
        }),
        ('Metadata', {
            'fields': (),
            'classes': ('collapse',),
            'description': 'Timestamps and other metadata.'
        }),
    )

    def save_model(self, request, obj, form, change):
        try:
            obj.save()
        except ValidationError as e:
            for field, errors in e.error_dict.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}" if field != '__all__' else error)
            raise

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class UserExclusivePriceAdmin(admin.ModelAdmin):
    list_display = ('user', 'item', 'discount_percentage', 'created_at')
    search_fields = ('user__email', 'item__sku')
    list_filter = ('created_at',)
    ordering = ('user', 'item')
    autocomplete_fields = ['user', 'item']
    readonly_fields = ('created_at',)

    fieldsets = (
        ('Basic Information', {
            'fields': ('user', 'item', 'discount_percentage'),
            'description': 'Core discount details.'
        }),
        ('Metadata', {
            'fields': (),
            'classes': ('collapse',),
            'description': 'Timestamps and other metadata.'
        }),
    )

    def save_model(self, request, obj, form, change):
        try:
            obj.save()
        except ValidationError as e:
            for field, errors in e.error_dict.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}" if field != '__all__' else error)
            raise

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 1
    fields = ('item', 'pricing_tier', 'quantity', 'unit_type', 'per_unit_price', 'per_pack_price', 'subtotal', 'total_cost')
    readonly_fields = ('subtotal', 'total_cost')
    autocomplete_fields = ['item', 'pricing_tier', 'user_exclusive_price']

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class CartAdmin(admin.ModelAdmin):
    list_display = ('user', 'subtotal', 'vat', 'discount', 'total', 'created_at', 'updated_at')
    search_fields = ('user__email',)
    list_filter = ('created_at', 'updated_at')
    ordering = ('user', 'created_at')
    inlines = [CartItemInline]
    readonly_fields = ('subtotal', 'total', 'created_at', 'updated_at')

    fieldsets = (
        ('Basic Information', {
            'fields': ('user',),
            'description': 'Core cart details.'
        }),
        ('Pricing Details', {
            'fields': ('subtotal', 'vat', 'discount', 'total'),
            'classes': ('inline-group',),
            'description': 'Cart pricing information.'
        }),
        ('Metadata', {
            'fields': (),
            'classes': ('collapse',),
            'description': 'Timestamps and other metadata.'
        }),
    )

    def save_model(self, request, obj, form, change):
        try:
            obj.save()
        except ValidationError as e:
            for field, errors in e.error_dict.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}" if field != '__all__' else error)
            raise

    def save_related(self, request, form, formsets, change):
        try:
            super().save_related(request, form, formsets, change)
        except ValidationError as e:
            for field, errors in e.error_dict.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}" if field != '__all__' else error)
            raise

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class CartItemAdmin(admin.ModelAdmin):
    list_display = ('cart', 'item', 'pricing_tier', 'quantity', 'unit_type', 'per_unit_price', 'per_pack_price', 'subtotal', 'total_cost', 'created_at')
    search_fields = ('cart__user__email', 'item__sku', 'pricing_tier__product_variant__name')
    list_filter = ('unit_type', 'created_at', 'updated_at')
    ordering = ('cart', 'item')
    autocomplete_fields = ['cart', 'item', 'pricing_tier', 'user_exclusive_price']
    readonly_fields = ('subtotal', 'total_cost', 'created_at', 'updated_at')

    fieldsets = (
        ('Basic Information', {
            'fields': ('cart', 'item', 'pricing_tier'),
            'description': 'Core cart item details.'
        }),
        ('Quantity and Pricing', {
            'fields': ('quantity', 'unit_type', 'per_unit_price', 'per_pack_price', 'subtotal', 'total_cost'),
            'classes': ('inline-group',),
            'description': 'Specify quantity and pricing details.'
        }),
        ('Metadata', {
            'fields': (),
            'classes': ('collapse',),
            'description': 'Timestamps and other metadata.'
        }),
    )

    def save_model(self, request, obj, form, change):
        try:
            obj.save()
        except ValidationError as e:
            for field, errors in e.error_dict.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}" if field != '__all__' else error)
            raise

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 1
    fields = ('item', 'pricing_tier', 'quantity', 'unit_type', 'per_unit_price', 'per_pack_price', 'total_cost')
    readonly_fields = ('total_cost',)
    autocomplete_fields = ['item', 'pricing_tier', 'user_exclusive_price']

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'status', 'total_amount', 'payment_status', 'created_at')
    search_fields = ('user__email', 'transaction_id')
    list_filter = ('status', 'payment_status', 'created_at')
    ordering = ('-created_at',)
    inlines = [OrderItemInline]
    autocomplete_fields = ['user']
    readonly_fields = ('total_amount', 'created_at')

    fieldsets = (
        ('Basic Information', {
            'fields': ('user', 'status', 'payment_status'),
            'description': 'Core order details.'
        }),
        ('Details', {
            'fields': ('total_amount', 'shipping_address', 'payment_method', 'transaction_id'),
            'description': 'Order and payment information.'
        }),
        ('Metadata', {
            'fields': (),
            'classes': ('collapse',),
            'description': 'Timestamps and other metadata.'
        }),
    )

    def save_model(self, request, obj, form, change):
        try:
            obj.save()
        except ValidationError as e:
            for field, errors in e.error_dict.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}" if field != '__all__' else error)
            raise

    def save_related(self, request, form, formsets, change):
        try:
            super().save_related(request, form, formsets, change)
        except ValidationError as e:
            for field, errors in e.error_dict.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}" if field != '__all__' else error)
            raise

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'item', 'pricing_tier', 'quantity', 'unit_type', 'per_unit_price', 'per_pack_price', 'total_cost', 'created_at')
    search_fields = ('order__user__email', 'item__sku', 'pricing_tier__product_variant__name')
    list_filter = ('unit_type', 'created_at')
    ordering = ('order', 'item')
    autocomplete_fields = ['order', 'item', 'pricing_tier', 'user_exclusive_price']
    readonly_fields = ('total_cost', 'created_at')

    fieldsets = (
        ('Basic Information', {
            'fields': ('order', 'item', 'pricing_tier'),
            'description': 'Core order item details.'
        }),
        ('Quantity and Pricing', {
            'fields': ('quantity', 'unit_type', 'per_unit_price', 'per_pack_price', 'total_cost'),
            'classes': ('inline-group',),
            'description': 'Specify quantity and pricing details.'
        }),
        ('Metadata', {
            'fields': (),
            'classes': ('collapse',),
            'description': 'Timestamps and other metadata.'
        }),
    )

    def save_model(self, request, obj, form, change):
        try:
            obj.save()
        except ValidationError as e:
            for field, errors in e.error_dict.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}" if field != '__all__' else error)
            raise

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

admin.site.register(Category, CategoryAdmin)
admin.site.register(Product, ProductAdmin)
admin.site.register(ProductImage)
admin.site.register(ProductVariant, ProductVariantAdmin)
admin.site.register(PricingTier, PricingTierAdmin)
admin.site.register(PricingTierData, PricingTierDataAdmin)
admin.site.register(TableField, TableFieldAdmin)
admin.site.register(Item, ItemAdmin)
admin.site.register(ItemImage, ItemImageAdmin)
admin.site.register(ItemData, ItemDataAdmin)
admin.site.register(UserExclusivePrice, UserExclusivePriceAdmin)
admin.site.register(Cart, CartAdmin)
admin.site.register(CartItem, CartItemAdmin)
admin.site.register(Order, OrderAdmin)
admin.site.register(OrderItem, OrderItemAdmin)