from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from .models import (
    Category, Product, ProductImage, ProductVariant, PricingTier, PricingTierData,
    TableField, Item, ItemImage, ItemData, UserExclusivePrice, Cart, CartItem, Order, OrderItem, BillingAddress, ShippingAddress
)
from decimal import Decimal, ROUND_HALF_UP
import logging
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.core.files.base import ContentFile
from django.urls import reverse, path
from django.utils.html import format_html
from backend_praco.utils import send_email

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

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }


class PricingTierInline(admin.TabularInline):
    model = PricingTier
    extra = 1
    fields = ('tier_type', 'range_start', 'range_end', 'no_end_range', 'created_at', 'edit_link')
    readonly_fields = ('created_at', 'edit_link')

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        class InlineForm(formset.form):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                if self.instance.pk:
                    for field_name in ['tier_type', 'range_start', 'range_end', 'no_end_range']:
                        self.fields[field_name].disabled = True
        formset.form = InlineForm
        return formset

    def edit_link(self, obj):
        if obj.pk:
            url = reverse('admin:%s_%s_change' % (obj._meta.app_label, obj._meta.model_name), args=[obj.pk])
            # Format the range display: "20+" for no_end_range, "1-20" otherwise
            range_str = f"{obj.range_start}+" if obj.no_end_range else f"{obj.range_start}-{obj.range_end}"
            return format_html(
                '<a class="btn btn-primary btn-sm" href="{}" target="_blank" onclick="window.open(\'{}\', \'_blank\', \'width=800,height=600\'); return false;">Edit {}</a>',
                url, url, range_str
            )
        return format_html('<span>-</span>')
    edit_link.short_description = "Edit Tier"

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        field = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == 'range_start':
            field.help_text = "Must be a positive number. First tier must start from 1."
        elif db_field.name == 'range_end':
            field.help_text = "Must be greater than range start unless 'No End Range' is checked."
        return field

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
            'description': 'Specify the quantity range for this tier. First tier must start from 1, and ranges must be sequential.'
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',),
            'description': 'Timestamps and other metadata.'
        }),
    )

    def save_model(self, request, obj, form, change):
        try:
            obj.full_clean()
            obj.save()
        except ValidationError as e:
            for field, errors in e.error_dict.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}" if field != '__all__' else error)
            return


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
    list_display = ('name', 'product', 'status', 'show_units_per', 'units_per_pack', 'units_per_pallet', 'created_at')
    search_fields = ('name', 'product__name')
    list_filter = ('status', 'show_units_per', 'created_at')
    ordering = ('product', 'name')
    inlines = [PricingTierInline]
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
        return [PricingTierInline]

    def save_model(self, request, obj, form, change):
        try:
            obj.full_clean()
            obj.save()
        except ValidationError as e:
            for field, errors in e.error_dict.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}" if field != '__all__' else error)
            return

    def save_related(self, request, form, formsets, change):
        try:
            super().save_related(request, form, formsets, change)
            obj = form.instance
            if obj.pk:  # Only validate if the object exists
                pricing_tiers = obj.pricing_tiers.all()
                pack_tiers = sorted([tier for tier in pricing_tiers if tier.tier_type == 'pack'], key=lambda x: x.range_start)
                pallet_tiers = sorted([tier for tier in pricing_tiers if tier.tier_type == 'pallet'], key=lambda x: x.range_start)

                if obj.show_units_per == 'pack':
                    if not pack_tiers:
                        messages.error(request, "At least one 'pack' pricing tier is required when show_units_per is 'Pack'.")
                        obj.status = 'draft'
                        obj.save()
                        return
                    if pallet_tiers:
                        messages.error(request, "Pallet pricing tiers are not allowed when show_units_per is 'Pack'.")
                        obj.status = 'draft'
                        obj.save()
                        return
                    if pack_tiers and pack_tiers[0].range_start != 1:
                        messages.error(request, "The first 'pack' pricing tier must start from 1.")
                        obj.status = 'draft'
                        obj.save()
                        return
                    for i in range(len(pack_tiers) - 1):
                        current = pack_tiers[i]
                        next_tier = pack_tiers[i + 1]
                        if current.no_end_range:
                            if i != len(pack_tiers) - 2:  # Ensure no_end_range is only on the last tier
                                messages.error(request, "A tier with 'No End Range' checked must be the last tier.")
                                obj.status = 'draft'
                                obj.save()
                                return
                        if not current.no_end_range and next_tier.range_start != current.range_end + 1:
                            messages.error(request, f"Pack pricing tiers must be sequential with no gaps. Range {current.range_start}-{'+' if current.no_end_range else current.range_end} does not connect to {next_tier.range_start}-{'+' if next_tier.no_end_range else next_tier.range_end}.")
                            obj.status = 'draft'
                            obj.save()
                            return
                elif obj.show_units_per == 'both':
                    if not pack_tiers:
                        messages.error(request, "At least one 'pack' pricing tier is required when show_units_per is 'Both'.")
                        obj.status = 'draft'
                        obj.save()
                        return
                    if not pallet_tiers:
                        messages.error(request, "At least one 'pallet' pricing tier is required when show_units_per is 'Both'.")
                        obj.status = 'draft'
                        obj.save()
                        return
                    if pack_tiers and pack_tiers[0].range_start != 1:
                        messages.error(request, "The first 'pack' pricing tier must start from 1.")
                        obj.status = 'draft'
                        obj.save()
                        return
                    if pallet_tiers and pallet_tiers[0].range_start != 1:
                        messages.error(request, "The first 'pallet' pricing tier must start from 1.")
                        obj.status = 'draft'
                        obj.save()
                        return
                    for i in range(len(pack_tiers) - 1):
                        current = pack_tiers[i]
                        next_tier = pack_tiers[i + 1]
                        if current.no_end_range:
                            if i != len(pack_tiers) - 2:
                                messages.error(request, "A tier with 'No End Range' checked must be the last tier for pack.")
                                obj.status = 'draft'
                                obj.save()
                                return
                        if not current.no_end_range and next_tier.range_start != current.range_end + 1:
                            messages.error(request, f"Pack pricing tiers must be sequential with no gaps. Range {current.range_start}-{'+' if current.no_end_range else current.range_end} does not connect to {next_tier.range_start}-{'+' if next_tier.no_end_range else next_tier.range_end}.")
                            obj.status = 'draft'
                            obj.save()
                            return
                    for i in range(len(pallet_tiers) - 1):
                        current = pallet_tiers[i]
                        next_tier = pallet_tiers[i + 1]
                        if current.no_end_range:
                            if i != len(pallet_tiers) - 2:
                                messages.error(request, "A tier with 'No End Range' checked must be the last tier for pallet.")
                                obj.status = 'draft'
                                obj.save()
                                return
                        if not current.no_end_range and next_tier.range_start != current.range_end + 1:
                            messages.error(request, f"Pallet pricing tiers must be sequential with no gaps. Range {current.range_start}-{'+' if current.no_end_range else current.range_end} does not connect to {next_tier.range_start}-{'+' if next_tier.no_end_range else next_tier.range_end}.")
                            obj.status = 'draft'
                            obj.save()
                            return
                else:
                    messages.error(request, f"Invalid show_units_per value: {obj.show_units_per}")
                    obj.status = 'draft'
                    obj.save()
                    return
        except ValidationError as e:
            for field, errors in e.error_dict.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}" if field != '__all__' else error)
            obj.status = 'draft'
            obj.save()
            return


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


    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 1
    fields = ('item', 'pricing_tier', 'pack_quantity', 'user_exclusive_price', 'get_discount_percentage', 'get_price_per_unit', 'get_price_per_pack', 'get_subtotal', 'get_total', 'get_weight')
    readonly_fields = ('created_at', 'get_discount_percentage', 'get_price_per_unit', 'get_price_per_pack', 'get_subtotal', 'get_total', 'get_weight')
    autocomplete_fields = ['item', 'pricing_tier', 'user_exclusive_price']

    def get_discount_percentage(self, obj):
        return obj.user_exclusive_price.discount_percentage if obj.user_exclusive_price else Decimal('0.00')
    get_discount_percentage.short_description = "Discount Percentage"

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

class CartItemAdmin(admin.ModelAdmin):
    search_fields = ('cart__user__email', 'item__sku')
    list_display = ('cart', 'item', 'pricing_tier', 'pack_quantity', 'get_discount_percentage', 'get_price_per_unit', 'get_price_per_pack', 'get_subtotal', 'get_total', 'get_weight', 'created_at')
    list_filter = ('created_at', 'updated_at')
    readonly_fields = ('created_at', 'updated_at', 'get_discount_percentage', 'get_price_per_unit', 'get_price_per_pack', 'get_subtotal', 'get_total', 'get_weight')
    ordering = ('cart', 'item')
    autocomplete_fields = ['cart', 'item', 'pricing_tier', 'user_exclusive_price']

    fieldsets = (
        ('Basic Information', {
            'fields': ('cart', 'item', 'pricing_tier', 'pack_quantity'),
            'description': 'Core cart item details.'
        }),
        ('Pricing Details', {
            'fields': ('get_discount_percentage', 'get_price_per_unit', 'get_price_per_pack', 'get_subtotal', 'get_total', 'get_weight', 'user_exclusive_price'),
            'classes': ('inline-group',),
            'description': 'Pricing, weight, discount information, and discount percentage. Note: Calculated fields are automatically computed and read-only.'
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
            'description': 'Timestamps and other metadata.'
        }),
    )

    def get_discount_percentage(self, obj):
        return obj.user_exclusive_price.discount_percentage if obj.user_exclusive_price else Decimal('0.00')
    get_discount_percentage.short_description = "Discount Percentage"

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
            # Check if CartItem already exists
            existing_cart_item = CartItem.objects.filter(
                cart=obj.cart,
                item=obj.item,
                pricing_tier=obj.pricing_tier,
                unit_type=obj.unit_type
            ).first()
            
            if existing_cart_item and existing_cart_item.pk != obj.pk:
                # Update existing CartItem instead of creating new
                existing_cart_item.pack_quantity += obj.pack_quantity
                if obj.user_exclusive_price:
                    existing_cart_item.user_exclusive_price = obj.user_exclusive_price
                existing_cart_item.full_clean()
                existing_cart_item.save()
                obj = existing_cart_item
            else:
                # Save new or update existing CartItem
                obj.full_clean()
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

class CartAdmin(admin.ModelAdmin):
    list_display = ('user', 'get_subtotal', 'vat', 'discount', 'get_total', 'get_total_units', 'get_total_packs', 'get_total_weight', 'created_at', 'updated_at')
    search_fields = ('user__email',)
    list_filter = ('created_at', 'updated_at')
    ordering = ('user', 'created_at')
    inlines = [CartItemInline]
    readonly_fields = ('created_at', 'updated_at', 'get_subtotal', 'get_total', 'get_total_units', 'get_total_packs', 'get_total_weight')

    fieldsets = (
        ('Basic Information', {
            'fields': ('user',),
            'description': 'Core cart details.'
        }),
        ('Pricing Details', {
            'fields': ('get_subtotal', 'vat', 'discount', 'get_total', 'get_total_units', 'get_total_packs', 'get_total_weight'),
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

    def get_total_units(self, obj):
        total_units, _ = obj.calculate_total_units_and_packs()
        return total_units
    get_total_units.short_description = "Total Units"

    def get_total_packs(self, obj):
        _, total_packs = obj.calculate_total_units_and_packs()
        return total_packs
    get_total_packs.short_description = "Total Packs"

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

logger = logging.getLogger(__name__)

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 1
    fields = (
        'item', 'pricing_tier', 'pack_quantity', 'unit_type', 'user_exclusive_price',
        'get_price_per_unit', 'get_price_per_pack', 'get_subtotal', 'get_total', 'get_weight',
        'created_at', 'updated_at'
    )
    readonly_fields = (
        'unit_type', 'created_at', 'updated_at',
        'get_price_per_unit', 'get_price_per_pack', 'get_subtotal', 'get_total', 'get_weight'
    )
    autocomplete_fields = ['item', 'pricing_tier', 'user_exclusive_price']

    def get_price_per_unit(self, obj):
        try:
            pricing_data = PricingTierData.objects.filter(pricing_tier=obj.pricing_tier, item=obj.item).first()
            return pricing_data.price if pricing_data else Decimal('0.00')
        except Exception as e:
            # logger.error(f"Error getting price per unit for order item {obj.id}: {str(e)}")
            return Decimal('0.00')
    get_price_per_unit.short_description = "Price Per Unit"
    

    def get_price_per_pack(self, obj):
        try:
            pricing_data = PricingTierData.objects.filter(pricing_tier=obj.pricing_tier, item=obj.item).first()
            if pricing_data and obj.item.product_variant:
                return pricing_data.price * Decimal(obj.item.product_variant.units_per_pack)
            return Decimal('0.00')
        except Exception as e:
            # logger.error(f"Error getting price per pack for order item {obj.id}: {str(e)}")
            return Decimal('0.00')
    get_price_per_pack.short_description = "Price Per Pack"

    def get_subtotal(self, obj):
        try:
            pricing_data = PricingTierData.objects.filter(pricing_tier=obj.pricing_tier, item=obj.item).first()
            if pricing_data and obj.item.product_variant:
                units_per_pack = obj.item.product_variant.units_per_pack
                per_pack_price = pricing_data.price * Decimal(units_per_pack)
                return (per_pack_price * Decimal(obj.pack_quantity)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            return Decimal('0.00')
        except Exception as e:
            # logger.error(f"Error getting subtotal for order item {obj.id}: {str(e)}")
            return Decimal('0.00')   
    get_subtotal.short_description = "Subtotal"


    def get_total(self, obj):
        try:
            subtotal = self.get_subtotal(obj)
            discount_percentage = obj.user_exclusive_price.discount_percentage if obj.user_exclusive_price else Decimal('0.00')
            discount = discount_percentage / Decimal('100.00')
            return (subtotal * (Decimal('1.00') - discount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except Exception as e:
            # logger.error(f"Error getting total for order item {obj.id}: {str(e)}")
            return Decimal('0.00')
    get_total.short_description = "Total"
    

    def get_weight(self, obj):
        try:
            item_weight_kg = obj.convert_weight_to_kg(obj.item.weight, obj.item.weight_unit)
            total_units = obj.total_units
            return (item_weight_kg * Decimal(total_units)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except Exception as e:
            # logger.error(f"Error getting weight for order item {obj.id}: {str(e)}")
            return Decimal('0.00')

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }
    get_weight.short_description = "Weigth"
    

class OrderAdminForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = [
            'user', 'shipping_address', 'billing_address', 'status',
            'payment_status', 'payment_verified', 'transaction_id',
            'payment_receipt', 'refund_transaction_id', 'refund_payment_receipt',
            'vat', 'discount'
        ]  # Include only editable fields
        exclude = [
            'paid_receipt', 'refund_receipt', 'invoice', 'delivery_note',
            'payment_method', 'shipping_cost', 'created_at', 'updated_at'
        ]  # Explicitly exclude non-editable fields

    def clean_status(self):
        status = self.cleaned_data.get('status')
        status_map = {
            'pending': 'PENDING',
            'processing': 'PROCESSING',
            'shipped': 'SHIPPED',
            'delivered': 'DELIVERED',
            'cancelled': 'CANCELLED',
            'returned': 'RETURNED'
        }
        normalized = status.upper() if status else status
        if normalized in status_map:
            normalized = status_map[normalized]
        if normalized not in dict(Order.STATUS_CHOICES):
            raise ValidationError(f'"{status}" is not a valid choice.')
        return normalized

    def clean_payment_status(self):
        payment_status = self.cleaned_data.get('payment_status')
        payment_status_map = {
            'pending': 'PENDING',
            'completed': 'COMPLETED',
            'failed': 'FAILED',
            'refund': 'refund'
        }
        normalized = payment_status.upper() if payment_status else payment_status
        if normalized in payment_status_map:
            normalized = payment_status_map[normalized]
        if normalized not in dict(Order.PAYMENT_STATUS_CHOICES):
            raise ValidationError(f'"{payment_status}" is not a valid choice.')
        return normalized


class OrderAdmin(admin.ModelAdmin):
    form = OrderAdminForm
    list_display = (
        'user', 'status', 'payment_status', 'payment_method',
        'get_subtotal', 'vat', 'discount', 'shipping_cost', 'get_total',
        'get_total_units', 'get_total_packs', 'get_total_weight',
        'transaction_id', 'refund_transaction_id',
        'created_at', 'updated_at',
        'invoice_actions', 'delivery_note_actions',
        'paid_receipt_actions', 'refund_receipt_actions'
    )
    search_fields = (
        'user__email', 'shipping_address__street', 'billing_address__street',
        'transaction_id', 'refund_transaction_id'
    )
    list_filter = ('status', 'payment_status', 'payment_method', 'created_at', 'updated_at')
    ordering = ('-created_at',)
    inlines = [OrderItemInline]
    readonly_fields = (
        'payment_method', 'shipping_cost', 'invoice', 'delivery_note',
        'paid_receipt', 'refund_receipt', 'created_at', 'updated_at',
        'get_subtotal', 'get_total', 'get_total_units', 'get_total_packs',
        'get_total_weight'
    )
    
    fieldsets = (
        ('Basic Information', {
            'fields': (
                'user', 'status', 'payment_status', 'payment_method',
                'shipping_address', 'billing_address'
            ),
            'description': 'Core order details.'
        }),
        ('Pricing Details', {
            'fields': (
                'get_subtotal', 'vat', 'discount', 'shipping_cost', 'get_total',
                'get_total_units', 'get_total_packs', 'get_total_weight'
            ),
            'classes': ('inline-group',),
            'description': 'Pricing, units, weight, and discount information.'
        }),
        ('Payment Information', {
            'fields': (
                'payment_verified', 'transaction_id', 'payment_receipt',
                'refund_transaction_id', 'refund_payment_receipt'
            ),
            'classes': ('inline-group',),
            'description': 'Payment and refund details.'
        }),
        ('Documents', {
            'fields': (
                'invoice', 'invoice_actions',
                'delivery_note', 'delivery_note_actions',
                'paid_receipt', 'paid_receipt_actions',
                'refund_receipt', 'refund_receipt_actions'
            ),
            'classes': ('inline-group',),
            'description': 'Generated documents for the order (read-only).'
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
            'description': 'Timestamps and other metadata.'
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields) + ['invoice_actions', 'delivery_note_actions', 'paid_receipt_actions', 'refund_receipt_actions']
        if obj:
            readonly.extend(['paid_receipt', 'refund_receipt', 'invoice', 'delivery_note', 'payment_method', 'shipping_cost'])
        return readonly

    def get_subtotal(self, obj):
        try:
            return f"€{obj.calculate_subtotal().quantize(Decimal('0.01')):.2f}"
        except Exception as e:
            logger.error(f"Error getting subtotal for order {obj.id}: {str(e)}")
            return "€0.00"
    get_subtotal.short_description = "Subtotal"

    def get_total(self, obj):
        try:
            return f"€{obj.calculate_total().quantize(Decimal('0.01')):.2f}"
        except Exception as e:
            logger.error(f"Error getting total for order {obj.id}: {str(e)}")
            return "€0.00"
    get_total.short_description = "Total"

    def get_total_weight(self, obj):
        try:
            return f"{obj.calculate_total_weight().quantize(Decimal('0.01')):.2f} kg"
        except Exception as e:
            logger.error(f"Error getting total weight for order {obj.id}: {str(e)}")
            return "0.00 kg"
    get_total_weight.short_description = "Weight"

    def get_total_units(self, obj):
        try:
            total_units, _ = obj.calculate_total_units_and_packs()
            return total_units
        except Exception as e:
            logger.error(f"Error getting total units for order {obj.id}: {str(e)}")
            return 0
        
    get_total_units.short_description = "Total Units"

    def get_total_packs(self, obj):
        try:
            _, total_packs = obj.calculate_total_units_and_packs()
            return total_packs
        except Exception as e:
            logger.error(f"Error getting total packs for order {obj.id}: {str(e)}")
            return 0
        
    get_total_packs.short_description = "Total Packs"

    def invoice_actions(self, obj):
        if not obj.id:
            return admin.utils.format_html('<span>Save order to view actions</span>')
        invoice_url = obj.invoice.url if obj.invoice else "#"
        buttons = [
            f'<a href="{invoice_url}" target="_blank">View</a>',
            f'<a href="{reverse("admin:send_invoice_email", args=[obj.id])}">Send Email</a>',
            f'<a href="{reverse("admin:regenerate_invoice", args=[obj.id])}">Regenerate</a>',
        ]
        return admin.utils.format_html(" | ".join(buttons))
    invoice_actions.short_description = "Invoice Actions"

    def delivery_note_actions(self, obj):
        if not obj.id:
            return admin.utils.format_html('<span>Save order to view actions</span>')
        delivery_note_url = obj.delivery_note.url if obj.delivery_note else "#"
        buttons = [
            f'<a href="{delivery_note_url}" target="_blank">View</a>',
            f'<a href="{reverse("admin:send_delivery_note_email", args=[obj.id])}">Send Email</a>',
            f'<a href="{reverse("admin:regenerate_delivery_note", args=[obj.id])}">Regenerate</a>',
        ]
        return admin.utils.format_html(" | ".join(buttons))
    delivery_note_actions.short_description = "Delivery Note Actions"

    def paid_receipt_actions(self, obj):
        if not obj.id:
            return admin.utils.format_html('<span>Save order to view actions</span>')
        paid_receipt_url = obj.paid_receipt.url if obj.paid_receipt else "#"
        buttons = [
            f'<a href="{paid_receipt_url}" target="_blank">View</a>',
            f'<a href="{reverse("admin:send_paid_receipt_email", args=[obj.id])}">Send Email</a>',
            f'<a href="{reverse("admin:regenerate_paid_receipt", args=[obj.id])}">Regenerate</a>',
        ]
        return admin.utils.format_html(" | ".join(buttons))
    paid_receipt_actions.short_description = "Paid Receipt Actions"

    def refund_receipt_actions(self, obj):
        if not obj.id:
            return admin.utils.format_html('<span>Save order to view actions</span>')
        refund_receipt_url = obj.refund_receipt.url if obj.refund_receipt else "#"
        buttons = [
            f'<a href="{refund_receipt_url}" target="_blank">View</a>',
            f'<a href="{reverse("admin:send_refund_receipt_email", args=[obj.id])}">Send Email</a>',
            f'<a href="{reverse("admin:regenerate_refund_receipt", args=[obj.id])}">Regenerate</a>',
        ]
        return admin.utils.format_html(" | ".join(buttons))
    refund_receipt_actions.short_description = "refund Receipt Actions"

    def save_model(self, request, obj, form, change):
        try:
            obj.full_clean()
            super().save_model(request, obj, form, change)
            obj.calculate_total()
            if obj.items.exists():
                obj.generate_and_save_pdfs()
                if obj.payment_verified or obj.payment_status in ['COMPLETED', 'refund']:
                    obj.generate_and_save_payment_receipts()
            messages.success(request, "Order saved successfully.")
        except ValidationError as e:
            for field, errors in e.error_dict.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}" if field != '__all__' else error)
            raise
        except Exception as e:
            logger.error(f"Error saving order {obj.id}: {str(e)}")
            messages.error(request, f"Error saving order: {str(e)}")
            raise

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<int:order_id>/send-invoice-email/', self.admin_site.admin_view(self.send_invoice_email), name='send_invoice_email'),
            path('<int:order_id>/send-delivery-note-email/', self.admin_site.admin_view(self.send_delivery_note_email), name='send_delivery_note_email'),
            path('<int:order_id>/send-paid-receipt-email/', self.admin_site.admin_view(self.send_paid_receipt_email), name='send_paid_receipt_email'),
            path('<int:order_id>/send-refund-receipt-email/', self.admin_site.admin_view(self.send_refund_receipt_email), name='send_refund_receipt_email'),
            path('<int:order_id>/regenerate-invoice/', self.admin_site.admin_view(self.regenerate_invoice), name='regenerate_invoice'),
            path('<int:order_id>/regenerate-delivery-note/', self.admin_site.admin_view(self.regenerate_delivery_note), name='regenerate_delivery_note'),
            path('<int:order_id>/regenerate-paid-receipt/', self.admin_site.admin_view(self.regenerate_paid_receipt), name='regenerate_paid_receipt'),
            path('<int:order_id>/regenerate-refund-receipt/', self.admin_site.admin_view(self.regenerate_refund_receipt), name='regenerate_refund_receipt'),
        ]
        return custom_urls + urls

    def send_invoice_email(self, request, order_id):
        order = self.get_object(request, order_id)
        if not order or not order.invoice:
            self.message_user(request, "No invoice available to send.", level=messages.ERROR)
            return self.redirect_to_changelist()

        user_name = order.user.get_full_name() or order.user.username
        subject = f"Invoice for Order #{order.id}"
        body = (
            f'<p>Dear {user_name},</p>'
            f'<p>Thank you for your purchase with Praco Packaging.</p>'
            f'<p>Please find attached the invoice for your order #{order.id}.</p>'
        )
        attachments = [(f'invoice_order_{order.id}.pdf', order.invoice.read(), 'application/pdf')]

        success = send_email(subject, body, order.user.email, is_html=True, attachments=attachments)
        if success:
            self.message_user(request, f"Invoice email sent to {order.user.email}.")
        else:
            self.message_user(request, f"Error sending invoice email to {order.user.email}.", level=messages.ERROR)
        return self.redirect_to_changelist()

    def send_delivery_note_email(self, request, order_id):
        order = self.get_object(request, order_id)
        if not order or not order.delivery_note:
            self.message_user(request, "No delivery note available to send.", level=messages.ERROR)
            return self.redirect_to_changelist()

        subject = f"Delivery Note for Order #{order.id}"
        body = (
            f'<p>Dear Team,</p>'
            f'<p>Please find attached the delivery note for order #{order.id} from Praco Packaging.</p>'
            f'<p>For any inquiries, please contact our logistics team at <a href="mailto:logistics@pracopackaging.com" class="text-blue-600 hover:underline">logistics@pracopackaging.com</a>.</p>'
        )
        attachments = [(f'delivery_note_order_{order.id}.pdf', order.delivery_note.read(), 'application/pdf')]

        success = send_email(subject, body, 'siddiqui.faizmuhammad@gmail.com', is_html=True, attachments=attachments)
        if success:
            self.message_user(request, "Delivery note email sent to siddiqui.faizmuhammad@gmail.com.")
        else:
            self.message_user(request, "Error sending delivery note email.", level=messages.ERROR)
        return self.redirect_to_changelist()

    def send_paid_receipt_email(self, request, order_id):
        order = self.get_object(request, order_id)
        if not order or not order.paid_receipt:
            self.message_user(request, "No paid receipt available to send.", level=messages.ERROR)
            return self.redirect_to_changelist()

        user_name = order.user.get_full_name() or order.user.username
        subject = f"Payment Receipt for Order #{order.id}"
        body = (
            f'<p>Dear {user_name},</p>'
            f'<p>Thank you for your payment to Praco Packaging.</p>'
            f'<p>Please find attached the payment receipt for your order #{order.id}.</p>'
        )
        attachments = [(f'paid_receipt_order_{order.id}.pdf', order.paid_receipt.read(), 'application/pdf')]

        success = send_email(subject, body, order.user.email, is_html=True, attachments=attachments)
        if success:
            self.message_user(request, f"Payment receipt email sent to {order.user.email}.")
        else:
            self.message_user(request, f"Error sending payment receipt email to {order.user.email}.", level=messages.ERROR)
        return self.redirect_to_changelist()

    def send_refund_receipt_email(self, request, order_id):
        order = self.get_object(request, order_id)
        if not order or not order.refund_receipt:
            self.message_user(request, "No refund receipt available to send.", level=messages.ERROR)
            return self.redirect_to_changelist()

        user_name = order.user.get_full_name() or order.user.username
        subject = f"Refund Receipt for Order #{order.id}"
        body = (
            f'<p>Dear {user_name},</p>'
            f'<p>We have processed a refund for your order #{order.id} with Praco Packaging.</p>'
            f'<p>Please find attached the refund receipt for your records.</p>'
        )
        attachments = [(f'refund_receipt_order_{order.id}.pdf', order.refund_receipt.read(), 'application/pdf')]

        success = send_email(subject, body, order.user.email, is_html=True, attachments=attachments)
        if success:
            self.message_user(request, f"Refund receipt email sent to {order.user.email}.")
        else:
            self.message_user(request, f"Error sending refund receipt email to {order.user.email}.", level=messages.ERROR)
        return self.redirect_to_changelist()

    def regenerate_invoice(self, request, order_id):
        order = self.get_object(request, order_id)
        if not order:
            self.message_user(request, "Order not found.", level=messages.ERROR)
            return self.redirect_to_changelist()

        try:
            invoice_buffer = order.generate_invoice_pdf()
            if invoice_buffer:
                if order.invoice:
                    order.invoice.delete(save=False)
                order.invoice.save(
                    f'invoice_order_{order.id}.pdf',
                    ContentFile(invoice_buffer.getvalue()),
                    save=True
                )
                invoice_buffer.close()
                logger.info(f"Invoice regenerated for order {order.id}")
                self.message_user(request, "Invoice regenerated successfully.")
            else:
                logger.warning(f"Invoice regeneration failed for order {order.id}")
                self.message_user(request, "Failed to regenerate invoice.", level=messages.ERROR)
        except Exception as e:
            logger.error(f"Error regenerating invoice for order {order.id}: {str(e)}")
            self.message_user(request, f"Error regenerating invoice: {str(e)}", level=messages.ERROR)
        return self.redirect_to_changelist()

    def regenerate_delivery_note(self, request, order_id):
        order = self.get_object(request, order_id)
        if not order:
            self.message_user(request, "Order not found.", level=messages.ERROR)
            return self.redirect_to_changelist()

        try:
            delivery_note_buffer = order.generate_delivery_note_pdf()
            if delivery_note_buffer:
                if order.delivery_note:
                    order.delivery_note.delete(save=False)
                order.delivery_note.save(
                    f'delivery_note_order_{order.id}.pdf',
                    ContentFile(delivery_note_buffer.getvalue()),
                    save=True
                )
                delivery_note_buffer.close()
                logger.info(f"Delivery note regenerated for order {order.id}")
                self.message_user(request, "Delivery note regenerated successfully.")
            else:
                logger.warning(f"Delivery note regeneration failed for order {order.id}")
                self.message_user(request, "Failed to regenerate delivery note.", level=messages.ERROR)
        except Exception as e:
            logger.error(f"Error regenerating delivery note for order {order.id}: {str(e)}")
            self.message_user(request, f"Error regenerating delivery note: {str(e)}", level=messages.ERROR)
        return self.redirect_to_changelist()

    def regenerate_paid_receipt(self, request, order_id):
        order = self.get_object(request, order_id)
        if not order:
            self.message_user(request, "Order not found.", level=messages.ERROR)
            return self.redirect_to_changelist()

        try:
            paid_receipt_buffer = order.generate_paid_receipt_pdf()
            if paid_receipt_buffer:
                if order.paid_receipt:
                    order.paid_receipt.delete(save=False)
                order.paid_receipt.save(
                    f'paid_receipt_order_{order.id}.pdf',
                    ContentFile(paid_receipt_buffer.getvalue()),
                    save=True
                )
                paid_receipt_buffer.close()
                logger.info(f"Paid receipt regenerated for order {order.id}")
                self.message_user(request, "Paid receipt regenerated successfully.")
            else:
                logger.warning(f"Paid receipt regeneration failed for order {order.id}")
                self.message_user(request, "Failed to regenerate paid receipt.", level=messages.ERROR)
        except Exception as e:
            logger.error(f"Error regenerating paid receipt for order {order.id}: {str(e)}")
            self.message_user(request, f"Error regenerating paid receipt: {str(e)}", level=messages.ERROR)
        return self.redirect_to_changelist()
    
    def regenerate_refund_receipt(self, request, order_id):
        order = self.get_object(request, order_id)
        if not order:
            self.message_user(request, "Order not found.", level=messages.ERROR)
            return self.redirect_to_changelist()

        try:
            refund_receipt_buffer = order.generate_refund_receipt_pdf()
            if refund_receipt_buffer:
                if order.refund_receipt:
                    order.refund_receipt.delete(save=False)
                order.refund_receipt.save(
                    f'refund_receipt_order_{order.id}.pdf',
                    ContentFile(refund_receipt_buffer.getvalue()),
                    save=True
                )
                refund_receipt_buffer.close()
                logger.info(f"refund receipt regenerated for order {order.id}")
                self.message_user(request, "refund receipt regenerated successfully.")
            else:
                logger.warning(f"refund receipt regeneration failed for order {order.id}")
                self.message_user(request, "Failed to regenerate refund receipt.", level=messages.ERROR)
        except Exception as e:
            logger.error(f"Error regenerating refund receipt for order {order.id}: {str(e)}")
            self.message_user(request, f"Error regenerating refund receipt: {str(e)}", level=messages.ERROR)
        return self.redirect_to_changelist()
    
    def redirect_to_changelist(self):
        return HttpResponseRedirect(reverse('admin:ecommerce_order_changelist'))

class OrderItemAdmin(admin.ModelAdmin):
    list_display = (
        'order', 'item', 'pricing_tier', 'pack_quantity', 'unit_type',
        'get_price_per_unit', 'get_price_per_pack', 'get_subtotal', 'get_total',
        'get_weight', 'user_exclusive_price', 'created_at', 'updated_at'
    )
    search_fields = ('order__user__email', 'item__sku')
    list_filter = ('unit_type', 'created_at', 'updated_at')
    readonly_fields = (
        'unit_type', 'created_at', 'updated_at',
        'get_price_per_unit', 'get_price_per_pack', 'get_subtotal', 'get_total', 'get_weight'
    )
    ordering = ('order', 'item')
    autocomplete_fields = ['order', 'item', 'pricing_tier', 'user_exclusive_price']

    fieldsets = (
        ('Basic Information', {
            'fields': (
                'order', 'item', 'pricing_tier', 'pack_quantity', 'unit_type'
            ),
            'description': 'Core order item details.'
        }),
        ('Pricing Details', {
            'fields': (
                'get_price_per_unit', 'get_price_per_pack', 'get_subtotal',
                'get_total', 'get_weight', 'user_exclusive_price'
            ),
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
        try:
            pricing_data = PricingTierData.objects.filter(pricing_tier=obj.pricing_tier, item=obj.item).first()
            return pricing_data.price if pricing_data else Decimal('0.00')
        except Exception as e:
            # logger.error(f"Error getting price per unit for order item {obj.id}: {str(e)}")
            return Decimal('0.00')
        
    get_price_per_unit.short_description = "Price Per Unit"

    def get_price_per_pack(self, obj):
        try:
            pricing_data = PricingTierData.objects.filter(pricing_tier=obj.pricing_tier, item=obj.item).first()
            if pricing_data and obj.item.product_variant:
                return pricing_data.price * Decimal(obj.item.product_variant.units_per_pack)
            return Decimal('0.00')
        except Exception as e:
            # logger.error(f"Error getting price per pack for order item {obj.id}: {str(e)}")
            return Decimal('0.00')
    get_price_per_pack.short_description = "Price Per Pack"
    

    def get_subtotal(self, obj):
        try:
            pricing_data = PricingTierData.objects.filter(pricing_tier=obj.pricing_tier, item=obj.item).first()
            if pricing_data and obj.item.product_variant:
                units_per_pack = obj.item.product_variant.units_per_pack
                per_pack_price = pricing_data.price * Decimal(units_per_pack)
                return (per_pack_price * Decimal(obj.pack_quantity)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            return Decimal('0.00')
        except Exception as e:
            # logger.error(f"Error getting subtotal for order item {obj.id}: {str(e)}")
            return Decimal('0.00')
    get_price_per_unit.short_description = "Price Subtotal"
    

    def get_total(self, obj):
        try:
            subtotal = self.get_subtotal(obj)
            discount_percentage = obj.user_exclusive_price.discount_percentage if obj.user_exclusive_price else Decimal('0.00')
            discount = discount_percentage / Decimal('100.00')
            return (subtotal * (Decimal('1.00') - discount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except Exception as e:
            # logger.error(f"Error getting total for order item {obj.id}: {str(e)}")
            return Decimal('0.00')
    get_price_per_unit.short_description = "Price Total"
    

    def get_weight(self, obj):
        try:
            item_weight_kg = obj.convert_weight_to_kg(obj.item.weight, obj.item.weight_unit)
            total_units = obj.total_units
            return (item_weight_kg * Decimal(total_units)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except Exception as e:
            # logger.error(f"Error getting weight for order item {obj.id}: {str(e)}")
            return Decimal('0.00')
    get_price_per_unit.short_description = "Price Total"

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class ShippingAddressAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'first_name', 'last_name', 'telephone_number', 'street', 'city', 'country', 'created_at')
    list_filter = ('country', 'city', 'created_at')
    search_fields = ('first_name', 'last_name', 'telephone_number', 'street', 'city', 'postal_code', 'country', 'user__email')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': ('user', 'first_name', 'last_name', 'telephone_number', 'street', 'city', 'state', 'postal_code', 'country')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class BillingAddressAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'first_name', 'last_name', 'telephone_number', 'street', 'city', 'country', 'created_at')
    list_filter = ('country', 'city', 'created_at')
    search_fields = ('first_name', 'last_name', 'telephone_number', 'street', 'city', 'postal_code', 'country', 'user__email')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': ('user', 'first_name', 'last_name', 'telephone_number', 'street', 'city', 'state', 'postal_code', 'country')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

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
admin.site.register(BillingAddress, BillingAddressAdmin)
admin.site.register(ShippingAddress, ShippingAddressAdmin)