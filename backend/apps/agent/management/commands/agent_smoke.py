from django.core.management.base import BaseCommand, CommandError

from apps.repositories.models import Repository

from ...runtime import AgentError, PMCopilotRuntime


class Command(BaseCommand):
    help = "Run the six-intent PM Copilot smoke test with the configured real LLM."

    def add_arguments(self, parser):
        parser.add_argument("--case", type=int, choices=range(1, 7))

    def handle(self, *args, **options):
        repositories = list(
            Repository.objects.order_by("-stars").values_list("full_name", flat=True)[:2]
        )
        if len(repositories) < 2:
            raise CommandError("At least two repositories are required for Agent smoke.")
        questions = [
            "最近哪些编码智能体项目值得关注？",
            "推荐适合学习的编码智能体项目。",
            "哪些编码智能体项目更适合企业试用？",
            f"分析 {repositories[0]}。",
            f"比较 {repositories[0]} 和 {repositories[1]} 的学习与企业采用价值。",
            f"{repositories[0]} 的未来情况如何？",
        ]
        selected_case = options.get("case")
        if selected_case:
            questions = [questions[selected_case - 1]]
        runtime = PMCopilotRuntime()
        intents = []
        tool_calls = 0
        for offset, question in enumerate(questions, start=1):
            index = selected_case or offset
            try:
                result = runtime.chat(question)
            except AgentError as exc:
                raise CommandError(f"Agent smoke failed: case={index} code={exc.code}") from exc
            intents.append(result["intent"])
            tool_calls += result["trace"]["tool_count"]
            if result["status"] == "CURRENT_SIGNAL_ANALYSIS" and "%" in result["answer"]:
                raise CommandError("Forecast safety smoke failed.")
        self.stdout.write(
            self.style.SUCCESS(
                "Agent smoke passed: "
                f"cases={len(questions)} intents={len(set(intents))} tool_calls={tool_calls}"
            )
        )
