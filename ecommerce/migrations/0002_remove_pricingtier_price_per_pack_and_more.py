# Generated by Django 5.2 on 2025-04-19 08:14

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ecommerce', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='pricingtier',
            name='price_per_pack',
        ),
        migrations.RemoveField(
            model_name='pricingtier',
            name='price_per_unit',
        ),
        migrations.CreateModel(
            name='PricingTierData',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('price', models.DecimalField(decimal_places=2, help_text="Price per pack if tier_type is 'pack', per pallet if 'pallet'", max_digits=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pricing_tier_data', to='ecommerce.item')),
                ('pricing_tier', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pricing_data', to='ecommerce.pricingtier')),
            ],
            options={
                'verbose_name': 'pricing tier data',
                'verbose_name_plural': 'pricing tier data',
                'indexes': [models.Index(fields=['item', 'pricing_tier'], name='ecommerce_p_item_id_b5e459_idx'), models.Index(fields=['created_at'], name='ecommerce_p_created_c6dc28_idx')],
                'unique_together': {('item', 'pricing_tier')},
            },
        ),
    ]
