from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from .models import (
    Category, Product, ProductImage, ProductVariant, PricingTier, PricingTierData,
    TableField, Item, ItemImage, ItemData, UserExclusivePrice, Cart, CartItem, Order, OrderItem
)
from decimal import Decimal, ROUND_HALF_UP

class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'created_at', 'grok_side_view')
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
            'fields': ('created_at',),
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

    def grok_side_view(self, obj):
        """Grok Side View: Quick summary of the category."""
        return f"{obj.name} (Slug: {obj.slug})"
    grok_side_view.short_description = "Grok Side View"

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
    list_display = ('name', 'slug', 'category', 'is_new', 'created_at', 'grok_side_view')
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
            'fields': ('created_at',),
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

    def grok_side_view(self, obj):
        """Grok Side View: Quick summary of the product."""
        return f"{obj.name} in {obj.category.name}"
    grok_side_view.short_description = "Grok Side View"

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class PricingTierInline(admin.TabularInline):
    model = PricingTier
    extra = 1
    fields = ('tier_type', 'range_start', 'range_end', 'no_end_range', 'created_at')
    readonly_fields = ('created_at',)
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
    list_display = ('product_variant', 'tier_type', 'range_start', 'range_end', 'no_end_range', 'created_at', 'grok_side_view')
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
            'fields': ('created_at',),
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

    def grok_side_view(self, obj):
        """Grok Side View: Quick summary of the pricing tier."""
        range_str = f"{obj.range_start}-{'+' if obj.no_end_range else obj.range_end}"
        return f"{obj.tier_type.capitalize()} Tier: {range_str}"
    grok_side_view.short_description = "Grok Side View"

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
    fields = ('name', 'field_type', 'long_field', 'created_at')
    readonly_fields = ('created_at',)
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
    list_display = ('name', 'product', 'status', 'show_units_per', 'units_per_pack', 'units_per_pallet', 'created_at', 'grok_side_view')
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
            'fields': ('created_at',),
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

    def grok_side_view(self, obj):
        """Grok Side View: Quick summary of the product variant."""
        return f"{obj.name} (Units/Pack: {obj.units_per_pack}, Units/Pallet: {obj.units_per_pallet})"
    grok_side_view.short_description = "Grok Side View"

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }
        js = ('admin/js/product_variant_admin.js',)

class PricingTierDataInline(admin.TabularInline):
    model = PricingTierData
    extra = 1
    fields = ('pricing_tier', 'price', 'created_at')
    readonly_fields = ('created_at',)
    autocomplete_fields = ['pricing_tier']

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class PricingTierDataAdmin(admin.ModelAdmin):
    list_display = ('item', 'pricing_tier', 'price', 'created_at', 'grok_side_view')
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
            'fields': ('created_at',),
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

    def grok_side_view(self, obj):
        """Grok Side View: Quick summary of the pricing tier data."""
        return f"Price: {obj.price} for {obj.item.sku}"
    grok_side_view.short_description = "Grok Side View"

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class TableFieldAdmin(admin.ModelAdmin):
    list_display = ('name', 'product_variant', 'field_type', 'long_field', 'created_at', 'grok_side_view')
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
            'fields': ('created_at',),
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

    def grok_side_view(self, obj):
        """Grok Side View: Quick summary of the table field."""
        return f"{obj.name} ({obj.field_type}, {'Long' if obj.long_field else 'Short'})"
    grok_side_view.short_description = "Grok Side View"

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
    fields = ('field', 'value_text', 'value_number', 'value_image', 'created_at')
    readonly_fields = ('created_at',)
    autocomplete_fields = ['field']

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class ItemAdmin(admin.ModelAdmin):
    list_display = ('sku', 'product_variant', 'status', 'is_physical_product', 'track_inventory', 'stock', 'created_at', 'grok_side_view')
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
            'fields': ('created_at',),
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

    def grok_side_view(self, obj):
        """Grok Side View: Quick summary of the item."""
        return f"{obj.sku} ({obj.title or 'No Title'})"
    grok_side_view.short_description = "Grok Side View"

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class ItemImageAdmin(admin.ModelAdmin):
    list_display = ('item', 'image', 'created_at', 'grok_side_view')
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
            'fields': ('created_at',),
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

    def grok_side_view(self, obj):
        """Grok Side View: Quick summary of the item image."""
        return f"Image for {obj.item.sku}"
    grok_side_view.short_description = "Grok Side View"

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class ItemDataAdmin(admin.ModelAdmin):
    list_display = ('item', 'field', 'value_text', 'value_number', 'value_image', 'created_at', 'grok_side_view')
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
            'fields': ('created_at',),
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

    def grok_side_view(self, obj):
        """Grok Side View: Quick summary of the item data."""
        if obj.field.field_type == 'image' and obj.value_image:
            return f"{obj.field.name}: Image"
        return f"{obj.field.name}: {obj.value_text or obj.value_number or '-'}"
    grok_side_view.short_description = "Grok Side View"

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class UserExclusivePriceAdmin(admin.ModelAdmin):
    list_display = ('user', 'item', 'discount_percentage', 'created_at', 'grok_side_view')
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
            'fields': ('created_at',),
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

    def grok_side_view(self, obj):
        """Grok Side View: Quick summary of the user exclusive price."""
        return f"{obj.user.email} gets {obj.discount_percentage}% off {obj.item.sku}"
    grok_side_view.short_description = "Grok Side View"

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 1
    fields = ('item', 'pricing_tier', 'pack_quantity', 'user_exclusive_price', 'get_price_per_unit', 'get_price_per_pack', 'get_subtotal', 'get_total', 'get_weight')
    readonly_fields = ('created_at', 'get_price_per_unit', 'get_price_per_pack', 'get_subtotal', 'get_total', 'get_weight')
    autocomplete_fields = ['item', 'pricing_tier', 'user_exclusive_price']

    def get_price_per_unit(self, obj):
        pricing_data = PricingTierData.objects.filter(pricing_tier=obj.pricing_tier, item=obj.item).first()
        return pricing_data.price if pricing_data else Decimal('0.00')
    get_price_per_unit.short_description = "Price Per Unit"

    def get_price_per_pack(self, obj):
        pricing_data = PricingTierData.objects.filter(pricing_tier=obj.pricing_tier, item=obj.item).first()
        if pricing_data and obj.item.product_variant:
            return pricing_data.price * Decimal(obj.item.product_variant.units_per_pack)
        return Decimal('0.00')
    get_price_per_pack.short_description = "Price Per Pack"

    def get_subtotal(self, obj):
        pricing_data = PricingTierData.objects.filter(pricing_tier=obj.pricing_tier, item=obj.item).first()
        if pricing_data and obj.item.product_variant:
            units_per_pack = obj.item.product_variant.units_per_pack
            per_pack_price = pricing_data.price * Decimal(units_per_pack)
            return (per_pack_price * Decimal(obj.pack_quantity)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return Decimal('0.00')
    get_subtotal.short_description = "Subtotal"

    def get_total(self, obj):
        subtotal = self.get_subtotal(obj)
        discount_percentage = obj.user_exclusive_price.discount_percentage if obj.user_exclusive_price else Decimal('0.00')
        discount = discount_percentage / Decimal('100.00')
        return (subtotal * (Decimal('1.00') - discount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    get_total.short_description = "Total"

    def get_weight(self, obj):
        item_weight_kg = obj.convert_weight_to_kg(obj.item.weight, obj.item.weight_unit)
        total_units = obj.total_units
        return (item_weight_kg * Decimal(total_units)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    get_weight.short_description = "Weight"

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class CartAdmin(admin.ModelAdmin):
    list_display = ('user', 'get_subtotal', 'vat', 'discount', 'get_total', 'total_units', 'total_packs', 'get_total_weight', 'created_at', 'updated_at', 'grok_side_view')
    search_fields = ('user__email',)
    list_filter = ('created_at', 'updated_at')
    ordering = ('user', 'created_at')
    inlines = [CartItemInline]
    readonly_fields = ('created_at', 'updated_at', 'get_subtotal', 'get_total', 'total_units', 'total_packs', 'get_total_weight')

    fieldsets = (
        ('Basic Information', {
            'fields': ('user',),
            'description': 'Core cart details.'
        }),
        ('Pricing Details', {
            'fields': ('get_subtotal', 'vat', 'discount', 'get_total', 'total_units', 'total_packs', 'get_total_weight'),
            'classes': ('inline-group',),
            'description': 'Pricing, units, weight, and discount information.'
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
            'description': 'Timestamps and other metadata.'
        }),
    )

    def get_subtotal(self, obj):
        return obj.calculate_subtotal()
    get_subtotal.short_description = "Subtotal"

    def get_total(self, obj):
        return obj.calculate_total()
    get_total.short_description = "Total"

    def get_total_weight(self, obj):
        return obj.calculate_total_weight()
    get_total_weight.short_description = "Total Weight"

    def save_model(self, request, obj, form, change):
        try:
            obj.save()
        except ValidationError as e:
            for field, errors in e.error_dict.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}" if field != '__all__' else error)
            raise

    def grok_side_view(self, obj):
        """Grok Side View: Quick summary of the cart."""
        return f"Cart for {obj.user.email} (Total: {obj.calculate_total()})"
    grok_side_view.short_description = "Grok Side View"

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class CartItemAdmin(admin.ModelAdmin):
    search_fields = ('cart__user__email', 'item__sku')
    list_display = ('cart', 'item', 'pricing_tier', 'pack_quantity', 'get_price_per_unit', 'get_price_per_pack', 'get_subtotal', 'get_total', 'get_weight', 'created_at', 'grok_side_view')
    list_filter = ('created_at', 'updated_at')
    readonly_fields = ('created_at', 'updated_at', 'get_price_per_unit', 'get_price_per_pack', 'get_subtotal', 'get_total', 'get_weight')
    ordering = ('cart', 'item')
    autocomplete_fields = ['cart', 'item', 'pricing_tier', 'user_exclusive_price']

    fieldsets = (
        ('Basic Information', {
            'fields': ('cart', 'item', 'pricing_tier', 'pack_quantity'),
            'description': 'Core cart item details.'
        }),
        ('Pricing Details', {
            'fields': ('get_price_per_unit', 'get_price_per_pack', 'get_subtotal', 'get_total', 'get_weight', 'user_exclusive_price'),
            'classes': ('inline-group',),
            'description': 'Pricing, weight, and discount information. Note: Pricing and weight fields are automatically calculated and read-only.'
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
            'description': 'Timestamps and other metadata.'
        }),
    )

    def get_price_per_unit(self, obj):
        pricing_data = PricingTierData.objects.filter(pricing_tier=obj.pricing_tier, item=obj.item).first()
        return pricing_data.price if pricing_data else Decimal('0.00')
    get_price_per_unit.short_description = "Price Per Unit"

    def get_price_per_pack(self, obj):
        pricing_data = PricingTierData.objects.filter(pricing_tier=obj.pricing_tier, item=obj.item).first()
        if pricing_data and obj.item.product_variant:
            return pricing_data.price * Decimal(obj.item.product_variant.units_per_pack)
        return Decimal('0.00')
    get_price_per_pack.short_description = "Price Per Pack"

    def get_subtotal(self, obj):
        pricing_data = PricingTierData.objects.filter(pricing_tier=obj.pricing_tier, item=obj.item).first()
        if pricing_data and obj.item.product_variant:
            units_per_pack = obj.item.product_variant.units_per_pack
            per_pack_price = pricing_data.price * Decimal(units_per_pack)
            return (per_pack_price * Decimal(obj.pack_quantity)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return Decimal('0.00')
    get_subtotal.short_description = "Subtotal"

    def get_total(self, obj):
        subtotal = self.get_subtotal(obj)
        discount_percentage = obj.user_exclusive_price.discount_percentage if obj.user_exclusive_price else Decimal('0.00')
        discount = discount_percentage / Decimal('100.00')
        return (subtotal * (Decimal('1.00') - discount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    get_total.short_description = "Total"

    def get_weight(self, obj):
        item_weight_kg = obj.convert_weight_to_kg(obj.item.weight, obj.item.weight_unit)
        total_units = obj.total_units
        return (item_weight_kg * Decimal(total_units)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    get_weight.short_description = "Weight"

    def save_model(self, request, obj, form, change):
        try:
            obj.save()
        except ValidationError as e:
            for field, errors in e.error_dict.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}" if field != '__all__' else error)
            raise

    def grok_side_view(self, obj):
        """Grok Side View: Quick summary of the cart item."""
        return f"{obj.pack_quantity} pack of {obj.item.sku} (Total: {self.get_total(obj)})"
    grok_side_view.short_description = "Grok Side View"

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }
        
class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 1
    fields = ('item', 'pricing_tier', 'pack_quantity', 'unit_type', 'per_unit_price', 'per_pack_price', 'total_cost', 'user_exclusive_price', 'created_at')
    readonly_fields = ('created_at', 'per_unit_price', 'per_pack_price', 'total_cost')
    autocomplete_fields = ['item', 'pricing_tier', 'user_exclusive_price']

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'status', 'total_amount', 'payment_status', 'created_at', 'grok_side_view')
    search_fields = ('user__email', 'transaction_id')
    list_filter = ('status', 'payment_status', 'created_at')
    ordering = ('created_at', 'user')
    inlines = [OrderItemInline]
    autocomplete_fields = ['user']
    readonly_fields = ('created_at',)

    fieldsets = (
        ('Basic Information', {
            'fields': ('user', 'status', 'total_amount'),
            'description': 'Core order details.'
        }),
        ('Shipping and Payment', {
            'fields': ('shipping_address', 'payment_status', 'payment_method', 'transaction_id'),
            'classes': ('inline-group',),
            'description': 'Shipping and payment information.'
        }),
        ('Metadata', {
            'fields': ('created_at',),
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

    def grok_side_view(self, obj):
        """Grok Side View: Quick summary of the order."""
        return f"Order {obj.id} by {obj.user.email} (Status: {obj.status})"
    grok_side_view.short_description = "Grok Side View"

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'item', 'pricing_tier', 'quantity', 'unit_type', 'per_unit_price', 'per_pack_price', 'total_cost', 'created_at', 'grok_side_view')
    search_fields = ('order__user__email', 'item__sku')
    list_filter = ('unit_type', 'created_at')
    ordering = ('order', 'item')
    autocomplete_fields = ['order', 'item', 'pricing_tier', 'user_exclusive_price']
    readonly_fields = ('created_at', 'per_unit_price', 'per_pack_price', 'total_cost')

    fieldsets = (
        ('Basic Information', {
            'fields': ('order', 'item', 'pricing_tier', 'quantity', 'unit_type'),
            'description': 'Core order item details.'
        }),
        ('Pricing Details', {
            'fields': ('per_unit_price', 'per_pack_price', 'total_cost', 'user_exclusive_price'),
            'classes': ('inline-group',),
            'description': 'Pricing and discount information (dynamically calculated).'
        }),
        ('Metadata', {
            'fields': ('created_at',),
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

    def grok_side_view(self, obj):
        """Grok Side View: Quick summary of the order item."""
        return f"{obj.quantity} {obj.unit_type} of {obj.item.sku} (Total: {obj.total_cost})"
    grok_side_view.short_description = "Grok Side View"

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }
# Register all models with their respective admin classes
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