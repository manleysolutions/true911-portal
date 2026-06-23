"""Vendor adapters for the reconciliation framework.

Each adapter normalizes a vendor export into ``list[VendorRecord]``. Register a
new vendor by adding a module here that calls ``base.register(name, adapter)``;
the engine and CLI never reference a specific vendor.
"""
