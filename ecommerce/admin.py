from django.contrib import admin
from django import forms
from django.utils.safestring import mark_safe
from .models import Category, CategoryImage, Product, SubCategory, TableField, ProductVariant, ProductVariantData, UserExclusivePrice

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at', 'image_thumbnail')
    search_fields = ('name',)
    list_filter = ('created_at',)
    readonly_fields = ('image_thumbnail',)

    class CategoryImageInline(admin.TabularInline):
        model = CategoryImage
        extra = 1
        fields = ('image', 'image_preview', 'created_at')
        readonly_fields = ('image_preview', 'created_at')

        def image_preview(self, obj):
            if obj.image:
                return mark_safe(f'<img src="{obj.image.url}" width="100" height="100" />')
            return '-'
        image_preview.short_description = 'Preview'

    inlines = [CategoryImageInline]

    def image_thumbnail(self, obj):
        if obj.image:
            return mark_safe(f'<img src="{obj.image.url}" width="50" height="50" />')
        return '-'
    image_thumbnail.short_description = 'Image'

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('images')

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'is_new', 'created_at')
    search_fields = ('name', 'category__name')
    list_filter = ('category', 'is_new', 'created_at')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('category')

class TableFieldInline(admin.TabularInline):
    model = TableField
    extra = 1
    fields = ('name', 'field_type', 'created_at')
    readonly_fields = ('created_at',)

    def has_delete_permission(self, request, obj=None):
        if obj is None or not isinstance(obj, TableField):
            return True
        if ProductVariantData.objects.filter(field=obj).exists():
            return False
        return True

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('subcategory')

@admin.register(SubCategory)
class SubCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'product', 'created_at', 'table_fields_count')
    search_fields = ('name', 'product__name')
    list_filter = ('product', 'created_at')
    inlines = [TableFieldInline]

    def table_fields_count(self, obj):
        return TableField.objects.filter(subcategory=obj).count()
    table_fields_count.short_description = 'Number of Table Fields'

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        obj = form.instance
        if not TableField.objects.filter(subcategory=obj).exists():
            raise forms.ValidationError("At least one Table Field is required for a SubCategory.")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('product')

class ProductVariantDataInline(admin.TabularInline):
    model = ProductVariantData
    extra = 1
    # We'll dynamically set fields in get_formset
    fields = ('field',)

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        if obj:
            table_fields = TableField.objects.filter(subcategory=obj.subcategory).select_related('subcategory')
            if not table_fields.exists():
                raise forms.ValidationError("No Table Fields defined for this SubCategory.")

            # Dynamically set the fields attribute to include all table field names
            self.fields = ['field'] + [field.name for field in table_fields]

            class DynamicForm(formset.form):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self.fields['field'].queryset = table_fields
                    for field in table_fields:
                        if field.field_type == 'text':
                            self.fields[field.name] = forms.CharField(
                                required=False,
                                initial=self.initial.get('value_text', '') if field.name == self.initial.get('field_name') else ''
                            )
                        elif field.field_type == 'number':
                            self.fields[field.name] = forms.IntegerField(
                                required=False,
                                initial=self.initial.get('value_number', None) if field.name == self.initial.get('field_name') else None
                            )
                        elif field.field_type == 'image':
                            self.fields[field.name] = forms.ImageField(
                                required=False,
                                initial=self.initial.get('value_image', None) if field.name == self.initial.get('field_name') else None
                            )
                    self.fields.pop('value_text', None)
                    self.fields.pop('value_number', None)
                    self.fields.pop('value_image', None)

                def clean(self):
                    cleaned_data = super().clean()
                    field = cleaned_data.get('field')
                    if field:
                        field_name = field.name
                        value = cleaned_data.get(field_name)
                        if field.field_type == 'text':
                            cleaned_data['value_text'] = value if value else None
                            cleaned_data['value_number'] = None
                            cleaned_data['value_image'] = None
                        elif field.field_type == 'number':
                            cleaned_data['value_number'] = value if value else None
                            cleaned_data['value_text'] = None
                            cleaned_data['value_image'] = None
                        elif field.field_type == 'image':
                            cleaned_data['value_image'] = value if value else None
                            cleaned_data['value_text'] = None
                            cleaned_data['value_number'] = None
                    return cleaned_data

            for form in formset.forms:
                if form.instance.pk:
                    form.initial['field_name'] = form.instance.field.name
                    if form.instance.field.field_type == 'text':
                        form.initial['value_text'] = form.instance.value_text
                    elif form.instance.field.field_type == 'number':
                        form.initial['value_number'] = form.instance.value_number
                    elif form.instance.field.field_type == 'image':
                        form.initial['value_image'] = form.instance.value_image

            formset.form = DynamicForm
        return formset

@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ('subcategory', 'created_at')
    search_fields = ('subcategory__name',)
    list_filter = ('subcategory', 'created_at')
    inlines = [ProductVariantDataInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('subcategory__product').prefetch_related('data_entries__field')

@admin.register(TableField)
class TableFieldAdmin(admin.ModelAdmin):
    list_display = ('name', 'subcategory', 'field_type', 'created_at')
    search_fields = ('name', 'subcategory__name')
    list_filter = ('subcategory', 'field_type', 'created_at')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('subcategory')

@admin.register(ProductVariantData)
class ProductVariantDataAdmin(admin.ModelAdmin):
    list_display = ('variant', 'field', 'value_display', 'created_at')
    search_fields = ('variant__subcategory__name', 'field__name')
    list_filter = ('variant__subcategory', 'field__field_type', 'created_at')

    def value_display(self, obj):
        if obj.field.field_type == 'image' and obj.value_image:
            return mark_safe(f'<img src="{obj.value_image.url}" width="50" height="50" />')
        return obj.value_text or obj.value_number or '-'
    value_display.short_description = 'Value'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('variant__subcategory', 'field')

@admin.register(UserExclusivePrice)
class UserExclusivePriceAdmin(admin.ModelAdmin):
    list_display = ('user', 'product', 'exclusive_price', 'created_at')
    search_fields = ('user__username', 'product__name')
    list_filter = ('user', 'product', 'created_at')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'product')