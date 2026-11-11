"""Fixed site choice constructs only owned components; no effects at factory."""

import pytest
from lab_generate_skill.bootstrap.site_instance import build_site_instance
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.sites.shopping.worker_instance import ShoppingWorkerInstance
from lab_generate_skill.sites.shopping_admin.worker_instance import AdminWorkerInstance
from site_worker_fixtures import configuration


@pytest.mark.parametrize("site", ["shopping_admin", "shopping"])
def test_explicit_fixed_site_dispatch_without_staging_or_login(site: str) -> None:
    data = configuration().model_dump()
    data["site_id"] = site
    config = SiteWorkerConfiguration.model_validate(data)
    result = build_site_instance(config)
    if site == "shopping":
        assert isinstance(result, ShoppingWorkerInstance)
        assert result.instance.state == "new"
    else:
        assert isinstance(result, AdminWorkerInstance)
        assert result.instance.state == "new"


@pytest.mark.parametrize(
    "field,value",
    [
        ("site_id", "reddit"),
        ("site_id", "module.name"),
        ("apptainer", "/other/apptainer"),
    ],
)
def test_unknown_site_or_changed_shopping_binary_rejected_before_factory(
    field: str, value: str
) -> None:
    data = configuration().model_dump()
    data["site_id"] = "shopping"
    data[field] = value
    with pytest.raises(ValueError):
        build_site_instance(SiteWorkerConfiguration.model_validate(data))
