from rest_framework import serializers

from .item_types import validate_item_type_parent
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
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model = Vendor
        fields = '__all__'
        extra_kwargs = {
            'name': {'required': False},
            'invoice_type': {'required': False},
            'logo': {'required': False, 'allow_null': True},
        }

    def get_logo_url(self, obj):
        if not obj.logo:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(obj.logo.url)
        return obj.logo.url


class ItemTypeSerializer(serializers.ModelSerializer):
    parent_name = serializers.CharField(source='parent.name', read_only=True, allow_null=True)
    full_path = serializers.SerializerMethodField()

    class Meta:
        model = ItemType
        fields = '__all__'

    def get_full_path(self, obj):
        return obj.get_full_path()

    def validate_parent(self, value):
        instance = getattr(self, 'instance', None)
        validate_item_type_parent(instance, value)
        return value

    def validate(self, attrs):
        parent = attrs.get('parent', getattr(self.instance, 'parent', None) if self.instance else None)
        name = attrs.get('name', getattr(self.instance, 'name', None) if self.instance else None)
        if name:
            queryset = ItemType.objects.filter(name=name, parent=parent)
            if self.instance and self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                raise serializers.ValidationError({
                    'name': 'An item type with this name already exists under the selected parent.',
                })
        return attrs


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
    item_type_name = serializers.SerializerMethodField()

    def get_item_type_name(self, obj):
        if not obj.item_type_id:
            return ''
        return obj.item_type.get_full_path()

    class Meta:
        model = InventoryItem
        fields = '__all__'


class LineItemSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(source='invoice.invoice_number', read_only=True)
    vendor_name = serializers.CharField(source='invoice.vendor.name', read_only=True)
    invoice_date = serializers.DateField(source='invoice.invoice_date', read_only=True)
    item_type_name = serializers.SerializerMethodField()
    job_number = serializers.CharField(source='job.job_id', read_only=True)

    def get_item_type_name(self, obj):
        if not obj.item_type_id:
            return ''
        return obj.item_type.get_full_path()
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
