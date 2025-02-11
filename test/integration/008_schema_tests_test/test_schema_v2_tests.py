from test.integration.base import DBTIntegrationTest, FakeArgs, use_profile
import os

from dbt.task.test import TestTask
from dbt.exceptions import CompilationException
from dbt.contracts.results import TestStatus


class TestSchemaTests(DBTIntegrationTest):

    def setUp(self):
        DBTIntegrationTest.setUp(self)
        self.run_sql_file("seed.sql")
        self.run_sql_file("seed_failure.sql")

    @property
    def schema(self):
        return "schema_tests_008"

    @property
    def models(self):
        return "models-v2/models"

    def run_schema_validations(self):
        args = FakeArgs()
        test_task = TestTask(args, self.config)
        return test_task.run()

    def assertTestFailed(self, result):
        self.assertEqual(result.status, "fail")
        self.assertFalse(result.skipped)
        self.assertTrue(
            int(result.message) > 0,
            'test {} did not fail'.format(result.node.name)
        )

    def assertTestPassed(self, result):
        self.assertEqual(result.status, "pass")
        self.assertFalse(result.skipped)
        self.assertEqual(
            int(result.message), 0,
            'test {} failed'.format(result.node.name)
        )

    @use_profile('postgres')
    def test_postgres_schema_tests(self):
        results = self.run_dbt()
        self.assertEqual(len(results), 5)
        test_results = self.run_schema_validations()
        # If the disabled model's tests ran, there would be 20 of these.
        self.assertEqual(len(test_results), 19)

        for result in test_results:
            # assert that all deliberately failing tests actually fail
            if 'failure' in result.node.name:
                self.assertTestFailed(result)
            # assert that actual tests pass
            else:
                self.assertTestPassed(result)

        self.assertEqual(sum(x.message for x in test_results), 6)

    @use_profile('postgres')
    def test_postgres_schema_test_selection(self):
        results = self.run_dbt()
        self.assertEqual(len(results), 5)
        test_results = self.run_dbt(
            ['test', '--models', 'tag:table_favorite_color'])
        # 1 in table_copy, 4 in table_summary
        self.assertEqual(len(test_results), 5)
        for result in test_results:
            self.assertTestPassed(result)

        test_results = self.run_dbt(
            ['test', '--models', 'tag:favorite_number_is_pi'])
        self.assertEqual(len(test_results), 1)
        self.assertTestPassed(test_results[0])

        test_results = self.run_dbt(
            ['test', '--models', 'tag:table_copy_favorite_color'])
        self.assertEqual(len(test_results), 1)
        self.assertTestPassed(test_results[0])

    @use_profile('postgres')
    def test_postgres_schema_test_exclude_failures(self):
        results = self.run_dbt()
        self.assertEqual(len(results), 5)
        test_results = self.run_dbt(['test', '--exclude', 'tag:xfail'])
        # If the failed + disabled model's tests ran, there would be 20 of these.
        self.assertEqual(len(test_results), 13)
        for result in test_results:
            self.assertTestPassed(result)
        test_results = self.run_dbt(
            ['test', '--models', 'tag:xfail'], expect_pass=False)
        self.assertEqual(len(test_results), 6)
        for result in test_results:
            self.assertTestFailed(result)


class TestMalformedSchemaTests(DBTIntegrationTest):

    def setUp(self):
        DBTIntegrationTest.setUp(self)
        self.run_sql_file("seed.sql")

    @property
    def schema(self):
        return "schema_tests_008"

    @property
    def models(self):
        return "models-v2/malformed"

    def run_schema_validations(self):
        args = FakeArgs()

        test_task = TestTask(args, self.config)
        return test_task.run()

    @use_profile('postgres')
    def test_postgres_malformed_schema_strict_will_break_run(self):
        with self.assertRaises(CompilationException):
            self.run_dbt(strict=True)
        # even if strict = False!
        with self.assertRaises(CompilationException):
            self.run_dbt(strict=False)


class TestHooksInTests(DBTIntegrationTest):

    @property
    def schema(self):
        return "schema_tests_008"

    @property
    def models(self):
        # test ephemeral models so we don't need to do a run (which would fail)
        return "ephemeral"

    @property
    def project_config(self):
        return {
            'config-version': 2,
            "on-run-start": ["{{ exceptions.raise_compiler_error('hooks called in tests -- error') if execute }}"],
            "on-run-end": ["{{ exceptions.raise_compiler_error('hooks called in tests -- error') if execute }}"],
        }

    @use_profile('postgres')
    def test_postgres_hooks_dont_run_for_tests(self):
        # This would fail if the hooks ran
        results = self.run_dbt(['test', '--model', 'ephemeral'])
        self.assertEqual(len(results), 1)
        for result in results:
            self.assertEqual(result.status, "pass")
            self.assertFalse(result.skipped)
            self.assertEqual(
                int(result.message), 0,
                'test {} failed'.format(result.node.name)
            )


class TestCustomSchemaTests(DBTIntegrationTest):

    def setUp(self):
        DBTIntegrationTest.setUp(self)
        self.run_sql_file("seed.sql")

    @property
    def schema(self):
        return "schema_tests_008"

    @property
    def packages_config(self):
        return {
            'packages': [
                {
                    'git': 'https://github.com/fishtown-analytics/dbt-integration-project',
                    'revision': 'dbt/0.17.0',
                },
            ]
        }

    @property
    def project_config(self):
        # dbt-utils containts a schema test (equality)
        # dbt-integration-project contains a schema.yml file
        # both should work!
        return {
            'config-version': 2,
            "macro-paths": ["macros-v2/macros"],
        }

    @property
    def models(self):
        return "models-v2/custom"

    def run_schema_validations(self):
        args = FakeArgs()

        test_task = TestTask(args, self.config)
        return test_task.run()

    @use_profile('postgres')
    def test_postgres_schema_tests(self):
        self.run_dbt(["deps"])
        results = self.run_dbt()
        self.assertEqual(len(results), 4)

        test_results = self.run_schema_validations()
        self.assertEqual(len(test_results), 5)

        expected_failures = ['unique', 'every_value_is_blue']

        for result in test_results:
            if result.status == 'error':
                self.assertTrue(result.node['name'] in expected_failures)
        self.assertEqual(sum(x.message for x in test_results), 52)


class TestBQSchemaTests(DBTIntegrationTest):
    @property
    def schema(self):
        return "schema_tests_008"

    @property
    def models(self):
        return "models-v2/bq-models"

    @staticmethod
    def dir(path):
        return os.path.normpath(
            os.path.join('models-v2', path))

    def run_schema_validations(self):
        args = FakeArgs()

        test_task = TestTask(args, self.config)
        return test_task.run()

    @use_profile('bigquery')
    def test_schema_tests_bigquery(self):
        self.use_default_project({'data-paths': [self.dir('seed')]})
        self.assertEqual(len(self.run_dbt(['seed'])), 1)
        results = self.run_dbt()
        self.assertEqual(len(results), 1)
        test_results = self.run_schema_validations()
        self.assertEqual(len(test_results), 8)

        for result in test_results:
            # assert that all deliberately failing tests actually fail
            if 'failure' in result.node.name:
                self.assertEqual(result.status, 'fail')
                self.assertFalse(result.skipped)
                self.assertTrue(
                    int(result.message) > 0,
                    'test {} did not fail'.format(result.node.name)
                )
            # assert that actual tests pass
            else:
                self.assertEqual(result.status, 'pass')
                self.assertFalse(result.skipped)
                self.assertEqual(
                    int(result.message), 0,
                    'test {} failed'.format(result.node.name)
                )

        self.assertEqual(sum(x.message for x in test_results), 0)


class TestQuotedSchemaTestColumns(DBTIntegrationTest):
    @property
    def schema(self):
        return "schema_tests_008"

    @property
    def models(self):
        return "quote-required-models"

    @use_profile('postgres')
    def test_postgres_quote_required_column(self):
        results = self.run_dbt()
        self.assertEqual(len(results), 3)
        results = self.run_dbt(['test', '-m', 'model'])
        self.assertEqual(len(results), 2)
        results = self.run_dbt(['test', '-m', 'model_again'])
        self.assertEqual(len(results), 2)
        results = self.run_dbt(['test', '-m', 'model_noquote'])
        self.assertEqual(len(results), 2)
        results = self.run_dbt(['test', '-m', 'source:my_source'])
        self.assertEqual(len(results), 1)
        results = self.run_dbt(['test', '-m', 'source:my_source_2'])
        self.assertEqual(len(results), 2)


class TestVarsSchemaTests(DBTIntegrationTest):
    @property
    def schema(self):
        return "schema_tests_008"

    @property
    def models(self):
        return "models-v2/render_test_arg_models"

    @property
    def project_config(self):
        return {
            'config-version': 2,
            "macro-paths": ["macros-v2/macros"],
        }

    @use_profile('postgres')
    def test_postgres_argument_rendering(self):
        results = self.run_dbt()
        self.assertEqual(len(results), 1)
        results = self.run_dbt(['test', '--vars', '{myvar: foo}'])
        self.assertEqual(len(results), 1)
        self.run_dbt(['test'], expect_pass=False)


class TestSchemaCaseInsensitive(DBTIntegrationTest):
    @property
    def schema(self):
        return "schema_tests_008"

    @property
    def models(self):
        return "case-sensitive-models"

    @use_profile('postgres')
    def test_postgres_schema_lowercase_sql(self):
        results = self.run_dbt(strict=False)
        self.assertEqual(len(results), 2)
        results = self.run_dbt(['test', '-m', 'lowercase'], strict=False)
        self.assertEqual(len(results), 1)

    @use_profile('postgres')
    def test_postgres_schema_uppercase_sql(self):
        results = self.run_dbt(strict=False)
        self.assertEqual(len(results), 2)
        results = self.run_dbt(['test', '-m', 'uppercase'], strict=False)
        self.assertEqual(len(results), 1)


class TestSchemaTestContext(DBTIntegrationTest):
    @property
    def schema(self):
        return "schema_tests_008"

    @property
    def models(self):
        return "test-context-models"

    @property
    def project_config(self):
        return {
            'config-version': 2,
            "macro-paths": ["test-context-macros"],
            "vars": {
                'local_utils_dispatch_list': ['local_utils']
            }
        }

    @property
    def packages_config(self):
        return {
            "packages": [
                {
                    'local': 'local_utils'
                }
            ]
        }

    @use_profile('postgres')
    def test_postgres_test_context_tests(self):
        # This test tests the the TestContext and TestMacroNamespace
        # are working correctly
        self.run_dbt(['deps'])
        results = self.run_dbt(strict=False)
        self.assertEqual(len(results), 3)

        run_result = self.run_dbt(['test'], expect_pass=False)
        results = run_result.results
        results = sorted(results, key=lambda r: r.node.name)
        self.assertEqual(len(results), 4)
        # call_pkg_macro_model_c_
        self.assertEqual(results[0].status, TestStatus.Fail)
        # pkg_and_dispatch_model_c_
        self.assertEqual(results[1].status, TestStatus.Fail)
        # type_one_model_a_
        self.assertEqual(results[2].status, TestStatus.Fail)
        self.assertRegex(results[2].node.compiled_sql, r'union all')
        # type_two_model_a_
        self.assertEqual(results[3].status, TestStatus.Fail)
        self.assertEqual(results[3].node.config.severity, 'WARN')

class TestSchemaTestContextWithMacroNamespace(DBTIntegrationTest):
    @property
    def schema(self):
        return "schema_tests_008"

    @property
    def models(self):
        return "test-context-models2"

    @property
    def project_config(self):
        return {
            'config-version': 2,
            "macro-paths": ["test-context-macros2"],
            "dispatch": [
                {
                    "macro_namespace": "test_utils",
                    "search_order": ['local_utils', 'test_utils'],
                }
            ],
        }

    @property
    def packages_config(self):
        return {
            "packages": [
                {
                    'local': 'test_utils'
                },
                {
                    'local': 'local_utils'
                },
            ]
        }

    @use_profile('postgres')
    def test_postgres_test_context_with_macro_namespace(self):
        # This test tests the the TestContext and TestMacroNamespace
        # are working correctly
        self.run_dbt(['deps'])
        results = self.run_dbt(strict=False)
        self.assertEqual(len(results), 3)

        run_result = self.run_dbt(['test'], expect_pass=False)
        results = run_result.results
        results = sorted(results, key=lambda r: r.node.name)
        self.assertEqual(len(results), 4)
        # call_pkg_macro_model_c_
        self.assertEqual(results[0].status, TestStatus.Fail)
        # pkg_and_dispatch_model_c_
        self.assertEqual(results[1].status, TestStatus.Fail)
        # type_one_model_a_
        self.assertEqual(results[2].status, TestStatus.Fail)
        self.assertRegex(results[2].node.compiled_sql, r'union all')
        # type_two_model_a_
        self.assertEqual(results[3].status, TestStatus.Fail)
        self.assertEqual(results[3].node.config.severity, 'WARN')

class TestSchemaTestNameCollision(DBTIntegrationTest):
    @property
    def schema(self):
        return "schema_tests_008"

    @property
    def models(self):
        return "name_collision"

    def run_schema_tests(self):
        args = FakeArgs()
        test_task = TestTask(args, self.config)
        return test_task.run()

    @use_profile('postgres')
    def test_postgres_collision_test_names_get_hash(self):
        """The models should produce unique IDs with a has appended"""
        results = self.run_dbt()
        test_results = self.run_schema_tests()

        # both models and both tests run
        self.assertEqual(len(results), 2)
        self.assertEqual(len(test_results), 2)

        # both tests have the same unique id except for the hash
        expected_unique_ids = [
            'test.test.not_null_base_extension_id.2dbb9627b6',
            'test.test.not_null_base_extension_id.d70fc39f40'
            ]
        self.assertIn(test_results[0].node.unique_id, expected_unique_ids)
        self.assertIn(test_results[1].node.unique_id, expected_unique_ids)
