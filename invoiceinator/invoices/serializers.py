from rest_framework import serializers
from .models import DataRule, Vendor


class DataRuleSerializer(serializers.ModelSerializer):
    vendor = serializers.PrimaryKeyRelatedField(read_only=True)
    vendor_id = serializers.PrimaryKeyRelatedField(queryset=Vendor.objects.all(), write_only=True, source='vendor')

    class Meta:
        model = DataRule
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class VendorSerializer(serializers.ModelSerializer):
    data_rules = DataRuleSerializer(many=True, read_only=True)

    class Meta:
        model = Vendor
        fields = ['id', 'name', 'invoice_type', 'data_rules']
