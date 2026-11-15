# Changelog

## [Unreleased]

### Changed
- CR-017: `create_shipment()` in `src/shipping.py` now uses `calculate_shipping_cost()` instead of inline cost logic. Shipment costs for methods 1, 2, 3 and 4 now follow the full tariff table.
- CR-017: `create_shipment()` requires the keyword-only parameter `distance` (km); the hardcoded 200 km is removed.