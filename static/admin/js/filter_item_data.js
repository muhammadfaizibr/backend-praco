(function($) {
    $(document).ready(function() {
        // Function to filter field dropdowns based on ProductVariant
        function filterFields() {
            var productVariantId = null;
            var isItemAddPage = window.location.pathname.includes('/ecommerce/item/add/');
            var isProductVariantAddPage = window.location.pathname.includes('/ecommerce/productvariant/add/');
            var isProductVariantChangePage = window.location.pathname.match(/\/ecommerce\/productvariant\/\d+\/change\//);

            if (isItemAddPage) {
                // In ItemAdmin context, get ProductVariant ID from the dropdown
                productVariantId = $('#id_product_variant').val();
                if (!productVariantId) {
                    $('select[id*="field"]').each(function() {
                        $(this).prop('disabled', true).val('');
                        $(this).next('.help').remove();
                        $(this).after('<p class="help">Select a Product Variant to enable this field.</p>');
                    });
                    return;
                }
            } else if (isProductVariantAddPage) {
                // In ProductVariantAdmin add context, check if ProductVariant is saved
                var hiddenIdInput = $('input[name="id"]');
                if (hiddenIdInput.length && hiddenIdInput.val()) {
                    productVariantId = hiddenIdInput.val();
                }
            } else if (isProductVariantChangePage) {
                // In ProductVariantAdmin change context, extract ProductVariant ID from URL
                var match = window.location.pathname.match(/\/ecommerce\/productvariant\/(\d+)\/change\//);
                if (match) {
                    productVariantId = match[1];
                }
            }

            if (productVariantId) {
                // ProductVariant ID is available, fetch TableFields via AJAX
                $('select[id*="field"]').next('.help').remove();
                $('select[id*="field"]').each(function() {
                    var $select = $(this);
                    var selectedValue = $select.val();
                    $select.prop('disabled', false);

                    $.ajax({
                        url: '/admin/ecommerce/tablefield/autocomplete/',
                        data: {
                            'product_variant_id': productVariantId,
                            'q': ''
                        },
                        success: function(data) {
                            $select.find('option:not(:first)').remove();
                            $.each(data.results, function(index, item) {
                                var option = new Option(item.text, item.id, false, item.id === selectedValue);
                                $select.append(option);
                            });
                            if (selectedValue && !$select.find('option[value="' + selectedValue + '"]').length) {
                                $select.val('');
                            }
                        },
                        error: function() {
                            console.error('Error fetching TableFields');
                        }
                    });
                });
            } else if (isProductVariantAddPage) {
                // ProductVariant is not saved yet, use unsaved TableField data from the form
                $('select[id*="field"]').next('.help').remove();
                $('select[id*="field"]').each(function() {
                    var $select = $(this);
                    var selectedValue = $select.val();
                    $select.prop('disabled', false);

                    $select.find('option:not(:first)').remove();

                    var tableFields = [];
                    $('[id^="table_fields-"]').each(function() {
                        var $formsetRow = $(this);
                        if ($formsetRow.find('[name$="-DELETE"]').is(':checked')) {
                            return;
                        }
                        var name = $formsetRow.find('[name$="-name"]').val();
                        var fieldType = $formsetRow.find('[name$="-field_type"]').val();
                        var idInput = $formsetRow.find('[name$="-id"]').val();
                        var tempId = $formsetRow.attr('id');

                        if (name && fieldType) {
                            var text = `${name} (${fieldType})`;
                            tableFields.push({
                                id: idInput || tempId,
                                text: text
                            });
                        }
                    });

                    $.each(tableFields, function(index, item) {
                        var option = new Option(item.text, item.id, false, item.id === selectedValue);
                        $select.append(option);
                    });

                    if (tableFields.length === 0) {
                        $select.prop('disabled', true);
                        $select.after('<p class="help">Add Table Fields in the Table Field section to enable this field.</p>');
                    }
                });
            }
        }

        // Trigger filtering on page load and when the form changes
        filterFields();

        // Listen for ProductVariant selection in ItemAdmin
        $('#id_product_variant').on('change', filterFields);

        // Listen for changes in the formset
        $(document).on('formset:added', function(event, $row, formsetName) {
            if (formsetName === 'table_fields' || formsetName === 'items') {
                filterFields();
            }
        });
        $(document).on('formset:removed', function(event, $row, formsetName) {
            if (formsetName === 'table_fields' || formsetName === 'items') {
                filterFields();
            }
        });

        // Listen for changes in TableFieldInline fields
        $('[name$="-name"], [name$="-field_type"]').on('change', filterFields);
    });
})(django.jQuery);