(function($) {
    $(document).ready(function() {
        // Function to filter pricing_tier dropdowns based on ProductVariant
        function filterPricingTiers() {
            var productVariantId = null;
            var isItemAddPage = window.location.pathname.includes('/ecommerce/item/add/');
            var isProductVariantAddPage = window.location.pathname.includes('/ecommerce/productvariant/add/');
            var isProductVariantChangePage = window.location.pathname.match(/\/ecommerce\/productvariant\/\d+\/change\//);

            if (isItemAddPage) {
                // In ItemAdmin context, get ProductVariant ID from the dropdown
                productVariantId = $('#id_product_variant').val();
                if (!productVariantId) {
                    $('select[id*="pricing_tier"]').each(function() {
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
                // ProductVariant ID is available, fetch PricingTiers via AJAX
                $('select[id*="pricing_tier"]').next('.help').remove();
                $('select[id*="pricing_tier"]').each(function() {
                    var $select = $(this);
                    var selectedValue = $select.val();
                    $select.prop('disabled', false);

                    $.ajax({
                        url: '/admin/ecommerce/pricingtier/autocomplete/',
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
                            console.error('Error fetching PricingTiers');
                        }
                    });
                });
            } else if (isProductVariantAddPage) {
                // ProductVariant is not saved yet, use unsaved PricingTier data from the form
                $('select[id*="pricing_tier"]').next('.help').remove();
                $('select[id*="pricing_tier"]').each(function() {
                    var $select = $(this);
                    var selectedValue = $select.val();
                    $select.prop('disabled', false);

                    $select.find('option:not(:first)').remove();

                    var pricingTiers = [];
                    $('[id^="pricing_tiers-"]').each(function() {
                        var $formsetRow = $(this);
                        if ($formsetRow.find('[name$="-DELETE"]').is(':checked')) {
                            return;
                        }
                        var tierType = $formsetRow.find('[name$="-tier_type"]').val();
                        var rangeStart = $formsetRow.find('[name$="-range_start"]').val();
                        var rangeEnd = $formsetRow.find('[name$="-range_end"]').val();
                        var idInput = $formsetRow.find('[name$="-id"]').val();
                        var tempId = $formsetRow.attr('id');

                        if (tierType && rangeStart && rangeEnd) {
                            var text = `${tierType} (${rangeStart}-${rangeEnd})`;
                            pricingTiers.push({
                                id: idInput || tempId,
                                text: text
                            });
                        }
                    });

                    $.each(pricingTiers, function(index, item) {
                        var option = new Option(item.text, item.id, false, item.id === selectedValue);
                        $select.append(option);
                    });

                    if (pricingTiers.length === 0) {
                        $select.prop('disabled', true);
                        $select.after('<p class="help">Add Pricing Tiers in the Pricing Tier section to enable this field.</p>');
                    }
                });
            }
        }

        // Trigger filtering on page load and when the form changes
        filterPricingTiers();

        // Listen for ProductVariant selection in ItemAdmin
        $('#id_product_variant').on('change', filterPricingTiers);

        // Listen for changes in the formset
        $(document).on('formset:added', function(event, $row, formsetName) {
            if (formsetName === 'pricing_tiers' || formsetName === 'items') {
                filterPricingTiers();
            }
        });
        $(document).on('formset:removed', function(event, $row, formsetName) {
            if (formsetName === 'pricing_tiers' || formsetName === 'items') {
                filterPricingTiers();
            }
        });

        // Listen for changes in PricingTierInline fields
        $('[name$="-tier_type"], [name$="-range_start"], [name$="-range_end"]').on('change', filterPricingTiers);
    });
})(django.jQuery);