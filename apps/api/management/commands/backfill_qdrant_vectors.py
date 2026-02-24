from django.core.management.base import BaseCommand, CommandError

from apps.api.models import Answer, Question
from apps.api.vector_indexing import index_answer_content, index_question_content


class Command(BaseCommand):
    help = "Backfill existing questions and answers into Qdrant vector index."

    def add_arguments(self, parser):
        parser.add_argument(
            "--questions-only",
            action="store_true",
            help="Backfill questions only.",
        )
        parser.add_argument(
            "--answers-only",
            action="store_true",
            help="Backfill answers only.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Optional max records per content type.",
        )

    def handle(self, *args, **options):
        questions_only = options["questions_only"]
        answers_only = options["answers_only"]
        limit = options["limit"]

        if questions_only and answers_only:
            raise CommandError("Use either --questions-only or --answers-only, not both.")

        if limit is not None and limit <= 0:
            raise CommandError("--limit must be a positive integer.")

        process_questions = not answers_only
        process_answers = not questions_only

        question_processed = question_indexed = 0
        answer_processed = answer_indexed = 0

        if process_questions:
            question_processed, question_indexed = self._backfill_questions(limit)

        if process_answers:
            answer_processed, answer_indexed = self._backfill_answers(limit)

        self.stdout.write(self.style.SUCCESS("Qdrant backfill complete."))
        self.stdout.write(
            "Questions processed: "
            f"{question_processed}, indexed: {question_indexed}, "
            f"skipped: {question_processed - question_indexed}"
        )
        self.stdout.write(
            "Answers processed: "
            f"{answer_processed}, indexed: {answer_indexed}, "
            f"skipped: {answer_processed - answer_indexed}"
        )

    def _backfill_questions(self, limit: int | None) -> tuple[int, int]:
        queryset = Question.objects.order_by("id")
        if limit is not None:
            queryset = queryset[:limit]

        processed = 0
        indexed = 0

        for question in queryset.iterator(chunk_size=200):
            processed += 1
            if index_question_content(question):
                indexed += 1

        return processed, indexed

    def _backfill_answers(self, limit: int | None) -> tuple[int, int]:
        queryset = Answer.objects.order_by("id")
        if limit is not None:
            queryset = queryset[:limit]

        processed = 0
        indexed = 0

        for answer in queryset.iterator(chunk_size=200):
            processed += 1
            if index_answer_content(answer):
                indexed += 1

        return processed, indexed
