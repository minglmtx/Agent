"""Pure declared initial-state equality shared by initializer and receipt reader."""

from decimal import Decimal
import re
from .product_description_spec import ProductDescriptionSpec
from .product_seed_contract import ProductSeed, ProductState


def validate_product_fixture(task: ProductDescriptionSpec, seed: ProductSeed) -> None:
    task = ProductDescriptionSpec.model_validate(task)
    seed = ProductSeed.model_validate(seed)
    if (
        len(seed.scenario.products) != 1
        or task.store_id != 0
        or seed.scenario.source_task_id != task.task.source_task_id
        or seed.scenario.products[0].name != task.product_name
    ):
        raise ValueError("Fixture scope differs from the original single-product task")


def validate_product_initial_state(
    task: ProductDescriptionSpec, seed: ProductSeed, result: ProductState
) -> None:
    validate_product_fixture(task, seed)
    result = ProductState.model_validate(result)
    if result.product_id != task.product_id:
        raise ValueError("Measured product changed original ID")
    expected = seed.scenario.products[0]
    if (
        result.sku != expected.sku
        or result.name != expected.name
        or Decimal(result.price) != Decimal(expected.price)
        or Decimal(result.qty) != 0
        or Decimal(result.weight) != 0
        or result.is_in_stock
        or result.visibility != 1
        or result.status != 1
        or result.website_ids != (1,)
        or result.category_ids
        or result.type_id != "simple"
        or result.tax_class_id <= 0
        or result.tax_class_label != expected.tax_label
        or result.short_description not in (None, "")
        or result.description not in (None, "")
        or result.url_key
        != "gobrowse-pilot-" + re.sub("[^a-zA-Z0-9]+", "-", expected.name).lower()
    ):
        error = ValueError("Measured product differs from declared initial fixture")
        setattr(error, "product_state", result)
        raise error
