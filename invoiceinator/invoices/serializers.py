from rest_framework import serializers
from .models import (
    Contact,
    Invoice,
    InvoiceAutomationSettings,
    InventoryItem,
    Job,
    LineItem,
    ItemType,
    Vendor,
)


class VendorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vendor
        fields = '__all__'
        extra_kwargs = {
            'name': {'required': False},
            'invoice_type': {'required': False}
        }


class ItemTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemType
        fields = '__all__'


class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = '__all__'


class InvoiceAutomationSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceAutomationSettings
        fields = '__all__'
        read_only_fields = ('last_processed_at', 'updated_at')


class JobSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source='vendor.name', read_only=True)

    class Meta:
        model = Job
        fields = '__all__'


class InventoryItemSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source='vendor.name', read_only=True)
    item_type_name = serializers.CharField(source='item_type.name', read_only=True)

    class Meta:
        model = InventoryItem
        fields = '__all__'


class LineItemSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(source='invoice.invoice_number', read_only=True)
    vendor_name = serializers.CharField(source='invoice.vendor.name', read_only=True)
    invoice_date = serializers.DateField(source='invoice.invoice_date', read_only=True)
    item_type_name = serializers.CharField(source='item_type.name', read_only=True)
    job_number = serializers.CharField(source='job.job_id', read_only=True)
    job_name = serializers.CharField(source='job.name', read_only=True)
    inventory_item_name = serializers.CharField(source='inventory_item.name', read_only=True)

    class Meta:
        model = LineItem
        fields = '__all__'


class InvoiceSerializer(serializers.ModelSerializer):
    line_items = LineItemSerializer(many=True, read_only=True)
    vendor_name = serializers.CharField(source='vendor.name', read_only=True)
    contact_name = serializers.CharField(source='contact.name', read_only=True)
    line_item_count = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = '__all__'

    def get_line_item_count(self, obj):
        return obj.line_items.count()
