from django.contrib import admin
from django.utils.safestring import mark_safe
from .models import Category, Product, ProductImage, ProductVariant, TableField, Item, ItemImage, ItemData, UserExclusivePrice

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at', 'image_thumbnail')
    search_fields = ('name', 'description')
    list_filter = ('created_at',)
    readonly_fields = ('image_thumbnail',)
    fields = ('name', 'description', 'image', 'image_thumbnail')

    def image_thumbnail(self, obj):
        if obj.image:
            return mark_safe(f'<img src="{obj.image.url}" width="50" height="50" />')
        return '-'
    image_thumbnail.short_description = 'Image'

    def get_queryset(self, request):
        return super().get_queryset(request)

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'is_new', 'created_at')
    search_fields = ('name', 'category__name', 'description')
    list_filter = ('category', 'is_new', 'created_at')

    class ProductImageInline(admin.TabularInline):
        model = ProductImage
        extra = 1
        fields = ('image', 'image_preview', 'created_at')
        readonly_fields = ('image_preview', 'created_at')
        max_num = 5

        def image_preview(self, obj):
            if obj.image:
                return mark_safe(f'<img src="{obj.image.url}" width="100" height="100" />')
            return '-'
        image_preview.short_description = 'Preview'

        def get_queryset(self, request):
            return super().get_queryset(request)

    inlines = [ProductImageInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('category').prefetch_related('images')

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        obj = form.instance
        if obj.images.count() > 5:
            raise ValueError("A Product cannot have more than 5 images.")

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class TableFieldInline(admin.TabularInline):
    model = TableField
    extra = 1
    fields = ('name', 'field_type', 'created_at')
    readonly_fields = ('created_at',)

    def has_delete_permission(self, request, obj=None):
        if obj is None or not isinstance(obj, TableField):
            return True
        if ItemData.objects.filter(field=obj).exists():
            return False
        return True

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('product_variant')

@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ('name', 'product', 'created_at', 'table_fields_count')
    search_fields = ('name', 'product__name')
    list_filter = ('product', 'created_at')
    inlines = [TableFieldInline]

    def table_fields_count(self, obj):
        return TableField.objects.filter(product_variant=obj).count()
    table_fields_count.short_description = 'Number of Table Fields'

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        obj = form.instance
        if not TableField.objects.filter(product_variant=obj).exists():
            raise ValueError("At least one Table Field is required for a Product Variant.")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('product')

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

class ItemDataInline(admin.TabularInline):
    model = ItemData
    extra = 1
    fields = ('field', 'value_text', 'value_number', 'value_image', 'value_display', 'created_at')
    readonly_fields = ('value_display', 'created_at')

    def value_display(self, obj):
        if obj.field and obj.field.field_type == 'image' and obj.value_image:
            return mark_safe(f'<img src="{obj.value_image.url}" width="50" height="50" />')
        elif obj.field and obj.field.field_type == 'price' and obj.value_number is not None:
            return f"${obj.value_number:.2f}"  # Display price with 2 decimal places
        return obj.value_text or obj.value_number or '-'
    value_display.short_description = 'Value'

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        if obj and obj.product_variant:
            table_fields = TableField.objects.filter(product_variant=obj.product_variant).select_related('product_variant')
            if not table_fields.exists():
                self.extra = 0
                return formset
            formset.form.base_fields['field'].queryset = table_fields
        else:
            self.extra = 0
        return formset

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'field' and hasattr(request, '_item_obj') and request._item_obj and request._item_obj.product_variant:
            kwargs['queryset'] = TableField.objects.filter(product_variant=request._item_obj.product_variant).select_related('product_variant')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ('sku', 'product_variant', 'status', 'is_physical_product', 'track_inventory', 'stock', 'title', 'created_at')
    search_fields = ('sku', 'product_variant__name', 'title')
    list_filter = ('product_variant', 'status', 'is_physical_product', 'track_inventory', 'created_at')
    fields = (
        'product_variant', 'sku', 'status', 'is_physical_product', 'weight', 'weight_unit',
        'track_inventory', 'stock', 'title'
    )

    class ItemImageInline(admin.TabularInline):
        model = ItemImage
        extra = 1
        fields = ('image', 'image_preview', 'created_at')
        readonly_fields = ('image_preview', 'created_at')
        max_num = 5

        def image_preview(self, obj):
            if obj.image:
                return mark_safe(f'<img src="{obj.image.url}" width="100" height="50" />')
            return '-'
        image_preview.short_description = 'Preview'

        def get_queryset(self, request):
            return super().get_queryset(request)

    inlines = [ItemDataInline, ItemImageInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('product_variant__product').prefetch_related('data_entries__field', 'images')

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        obj = form.instance
        if obj.images.count() > 5:
            raise ValueError("An Item cannot have more than 5 images.")

    def get_form(self, request, obj=None, **kwargs):
        request._item_obj = obj
        return super().get_form(request, obj, **kwargs)

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

@admin.register(TableField)
class TableFieldAdmin(admin.ModelAdmin):
    list_display = ('name', 'product_variant', 'field_type', 'created_at')
    search_fields = ('name', 'product_variant__name')
    list_filter = ('product_variant', 'field_type', 'created_at')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('product_variant')

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

@admin.register(ItemData)
class ItemDataAdmin(admin.ModelAdmin):
    list_display = ('item', 'field', 'value_display', 'created_at')
    search_fields = ('item__sku', 'field__name')
    list_filter = ('item__product_variant', 'field__field_type', 'created_at')

    def value_display(self, obj):
        if obj.field.field_type == 'image' and obj.value_image:
            return mark_safe(f'<img src="{obj.value_image.url}" width="50" height="50" />')
        elif obj.field.field_type == 'price' and obj.value_number is not None:
            return f"${obj.value_number:.2f}"
        return obj.value_text or obj.value_number or '-'
    value_display.short_description = 'Value'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('item__product_variant', 'field')

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

@admin.register(UserExclusivePrice)
class UserExclusivePriceAdmin(admin.ModelAdmin):
    list_display = ('user', 'item', 'discount_percentage', 'created_at')
    search_fields = ('user__email', 'user__first_name', 'item__sku')
    list_filter = ('user', 'item__product_variant', 'created_at')
    fields = ('user', 'item', 'discount_percentage')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'item__product_variant')

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }