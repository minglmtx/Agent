"""Fixed browser file selection; absent for tasks without explicit delivery."""

from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.reddit_browser_initialization import (
    RedditNativeImageInitialization,
)
from lab_generate_skill.ports.browser_task_files import BrowserTaskFiles


def browser_task_files(
    configuration: BrowserWorkerConfiguration,
) -> BrowserTaskFiles | None:
    configuration = BrowserWorkerConfiguration.model_validate(configuration)
    if isinstance(configuration.initialization, RedditNativeImageInitialization):
        from lab_generate_skill.adapters.browsergym.task_files import (
            LocalBrowserTaskFiles,
        )

        return LocalBrowserTaskFiles(configuration.initialization.task_files)
    return None
