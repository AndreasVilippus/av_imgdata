import json
import shutil
import subprocess
import textwrap

import pytest


def run_node(script: str):
    if not shutil.which("node"):
        pytest.skip("node is required for UI runtime tests")
    result = subprocess.run(
        ["node", "-e", script],
        cwd=".",
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    output = result.stdout.strip()
    return json.loads(output) if output else {}


def mixin_runtime_script(mixin_path: str, test_body: str) -> str:
    return textwrap.dedent(
        f"""
        const fs = require('fs');
        const vm = require('vm');
        const assert = require('assert');

        const source = fs.readFileSync('{mixin_path}', 'utf8')
          .replace('export default', 'module.exports =');
        const sandbox = {{ module: {{ exports: {{}} }}, exports: {{}} }};
        vm.runInNewContext(source, sandbox, {{ filename: '{mixin_path}' }});
        const mixin = sandbox.module.exports;

        function createComponent(overrides = {{}}) {{
          const component = {{}};
          for (const [name, fn] of Object.entries(mixin.methods || {{}})) {{
            component[name] = fn.bind(component);
          }}
          const state = mixin.data ? mixin.data.call(component) : {{}};
          Object.assign(component, state);
          Object.assign(component, overrides);
          for (const [name, getter] of Object.entries(mixin.computed || {{}})) {{
            Object.defineProperty(component, name, {{
              get() {{ return getter.call(component); }},
              configurable: true,
            }});
          }}
          component.$avt = (key, fallback) => fallback || key;
          component.getResponseData = component.getResponseData || ((data) => (
            data && typeof data.data === 'object' && data.data ? data.data : {{}}
          ));
          component.getResponseDataObject = component.getResponseDataObject || ((data, key) => {{
            const root = component.getResponseData(data);
            return root && typeof root[key] === 'object' && root[key] ? root[key] : {{}};
          }});
          component.startNamedPolling = component.startNamedPolling || (() => {{}});
          component.stopNamedPolling = component.stopNamedPolling || (() => {{}});
          return component;
        }}

        (async () => {{
          {test_body}
        }})().catch((err) => {{
          console.error(err && err.stack ? err.stack : err);
          process.exit(1);
        }});
        """
    )


def test_face_match_poll_error_keeps_backend_owned_running_state_runtime():
    result = run_node(
        mixin_runtime_script(
            "ui/src/mixins/faceMatchMixin.js",
            """
            const events = [];
            const component = createComponent({
              faceMatchLoading: true,
              faceMatchProgress: { running: true },
              callDsmApi: async () => { throw new Error('network status 0'); },
              stopFaceMatchProgressPolling: () => events.push('stop'),
              fetchFaceMatchFindingsStatus: async () => events.push('findings-status'),
              syncFaceMatchTransferredCountFromProgress: () => {},
            });

            await component.fetchFaceMatchingProgress();

            assert.strictEqual(component.faceMatchLoading, true);
            assert.strictEqual(component.faceMatchProgress.running, true);
            assert.match(component.faceMatchProgress.message, /network status 0/);
            assert.deepStrictEqual(events, []);
            console.log(JSON.stringify({ loading: component.faceMatchLoading, events }));
            """
        )
    )

    assert result == {"loading": True, "events": []}


def test_face_match_final_backend_progress_releases_loading_runtime():
    result = run_node(
        mixin_runtime_script(
            "ui/src/mixins/faceMatchMixin.js",
            """
            const events = [];
            const component = createComponent({
              faceMatchLoading: true,
              faceMatchProgress: { running: true },
              callDsmApi: async () => ({ success: true, data: { running: false, finished: true } }),
              stopFaceMatchProgressPolling: () => events.push('stop'),
              fetchFaceMatchFindingsStatus: async () => events.push('findings-status'),
              syncFaceMatchTransferredCountFromProgress: () => {},
              resetFaceMatchSelectionState: () => events.push('reset-selection'),
            });

            await component.fetchFaceMatchingProgress();

            assert.strictEqual(component.faceMatchLoading, false);
            assert.deepStrictEqual(events, ['reset-selection', 'findings-status', 'stop']);
            console.log(JSON.stringify({ loading: component.faceMatchLoading, events }));
            """
        )
    )

    assert result["loading"] is False
    assert result["events"][-2:] == ["findings-status", "stop"]


def test_face_match_incomplete_worker_handoff_keeps_polling_runtime():
    result = run_node(
        mixin_runtime_script(
            "ui/src/mixins/faceMatchMixin.js",
            """
            const events = [];
            const previousProgress = {
              operation_id: 'face_match-existing',
              revision: 18750,
              running: true,
              finished: false,
              result: null,
            };
            const component = createComponent({
              faceMatchLoading: true,
              faceMatchProgress: previousProgress,
              callDsmApi: async () => ({
                success: true,
                data: {
                  operation_id: 'face_match-existing',
                  revision: 18754,
                  running: false,
                  finished: false,
                  stale: true,
                  result: null,
                },
              }),
              stopFaceMatchProgressPolling: () => events.push('stop'),
              fetchFaceMatchFindingsStatus: async () => events.push('findings-status'),
            });

            await component.fetchFaceMatchingProgress();

            assert.strictEqual(component.faceMatchLoading, true);
            assert.strictEqual(component.faceMatchProgress, previousProgress);
            assert.deepStrictEqual(events, []);
            console.log(JSON.stringify({ loading: component.faceMatchLoading, events }));
            """
        )
    )

    assert result == {"loading": True, "events": []}


def test_checks_poll_error_keeps_backend_owned_running_state_runtime():
    result = run_node(
        mixin_runtime_script(
            "ui/src/mixins/checksMixin.js",
            """
            const events = [];
            const component = createComponent({
              checksLoading: true,
              checksFindingsActionRunning: true,
              selectedChecksAction: 'findings',
              callDsmApi: async () => { throw new Error('network status 0'); },
              stopChecksProgressPolling: () => events.push('stop'),
            });

            await component.fetchChecksProgress();

            assert.strictEqual(component.checksLoading, true);
            assert.strictEqual(component.checksFindingsActionRunning, true);
            assert.match(component.checksStatusMessage, /network status 0/);
            assert.deepStrictEqual(events, []);
            console.log(JSON.stringify({ loading: component.checksLoading, findingsRunning: component.checksFindingsActionRunning, events }));
            """
        )
    )

    assert result == {"loading": True, "findingsRunning": True, "events": []}


def test_checks_final_backend_progress_releases_loading_runtime():
    result = run_node(
        mixin_runtime_script(
            "ui/src/mixins/checksMixin.js",
            """
            const events = [];
            const component = createComponent({
              checksLoading: true,
              checksFindingsActionRunning: true,
              selectedChecksAction: 'findings',
              callDsmApi: async () => ({ success: true, data: { running: false, finished: true } }),
              applyChecksProgress: () => events.push('apply-progress'),
              ensureChecksResultItemLoaded: async () => events.push('load-item'),
              stopChecksProgressPolling: () => events.push('stop'),
            });

            await component.fetchChecksProgress();

            assert.strictEqual(component.checksLoading, false);
            assert.strictEqual(component.checksFindingsActionRunning, false);
            assert.deepStrictEqual(events, ['apply-progress', 'load-item', 'stop']);
            console.log(JSON.stringify({ loading: component.checksLoading, findingsRunning: component.checksFindingsActionRunning, events }));
            """
        )
    )

    assert result["loading"] is False
    assert result["findingsRunning"] is False
    assert result["events"] == ["apply-progress", "load-item", "stop"]


def test_checks_position_replacement_requires_different_source_formats_runtime():
    result = run_node(
        mixin_runtime_script(
            "ui/src/mixins/checksMixin.js",
            """
            const component = createComponent({
              checksActionLocked: false,
            });
            const item = { review_type: 'position_deviations', image_path: '/volume1/photo/test.jpg' };

            assert.strictEqual(
              component.canReplaceChecksFacePosition(
                item,
                { source_format: 'ACD' },
                { source_format: 'ACD' },
              ),
              false
            );
            assert.strictEqual(
              component.canReplaceChecksFacePosition(
                item,
                { source_format: 'ACD' },
                { source_format: 'MWG_REGIONS' },
              ),
              true
            );
            console.log(JSON.stringify({ same: false, different: true }));
            """
        )
    )

    assert result == {"same": False, "different": True}


def test_checks_face_name_warning_applies_findings_update_runtime():
    result = run_node(
        mixin_runtime_script(
            "ui/src/mixins/checksMixin.js",
            """
            const events = [];
            const staleItem = {
              review_type: 'duplicate_faces',
              image_path: '/volume1/photo/duplicate.jpg',
            };
            const component = createComponent({
              checksCurrentItem: staleItem,
              checksCurrentIndex: 0,
              checksEntries: [staleItem],
              checksProgress: {},
              selectedChecksAction: 'findings',
              selectedChecksType: 'duplicate_faces',
              checksSkipNameMappingConfirm: true,
              canReplaceChecksFaceName: () => true,
              resetChecksDuplicateAssignmentState: () => events.push('reset-assignment'),
              loadChecksItemAtIndex: async (index) => events.push(['load', index]),
              showChecksPopup: (message) => events.push(['popup', message]),
              getChecksWarningPopupMessage: () => '',
              callChecksApi: async (_url, payload) => {
                events.push(['review_type', payload.review_type]);
                return {
                  success: true,
                  data: {
                    updated: false,
                    warning: 'checks:warning_face_replace_not_found',
                    findings_update: {
                      image_path: '/volume1/photo/duplicate.jpg',
                      image_entries: [],
                      count: 0,
                      status: 'finished',
                      save_only: true,
                    },
                  },
                };
              },
            });

            await component.replaceChecksMetadataFaceName({ name: 'Klaus Heine' }, 'Werner Kodantke');

            assert.strictEqual(component.checksCurrentItem, null);
            assert.deepStrictEqual(component.checksEntries, []);
            assert.strictEqual(component.checksStatusMessage, 'Face name could not be replaced in metadata.');
            assert.deepStrictEqual(events, [['review_type', 'duplicate_faces'], 'reset-assignment']);
            console.log(JSON.stringify({ entries: component.checksEntries.length, current: component.checksCurrentItem, events }));
            """
        )
    )

    assert result == {
        "entries": 0,
        "current": None,
        "events": [["review_type", "duplicate_faces"], "reset-assignment"],
    }


def test_cleanup_poll_error_keeps_backend_owned_running_state_runtime():
    result = run_node(
        mixin_runtime_script(
            "ui/src/mixins/cleanupMixin.js",
            """
            const events = [];
            const component = createComponent({
              cleanupLoading: true,
              cleanupProgress: { running: true },
              callDsmApi: async () => { throw new Error('network status 0'); },
              stopCleanupProgressPolling: () => events.push('stop'),
            });

            await component.fetchCleanupProgress();

            assert.strictEqual(component.cleanupLoading, true);
            assert.strictEqual(component.cleanupProgress.running, true);
            assert.match(component.cleanupProgress.message, /network status 0/);
            assert.deepStrictEqual(events, []);
            console.log(JSON.stringify({ loading: component.cleanupLoading, events }));
            """
        )
    )

    assert result == {"loading": True, "events": []}


def test_cleanup_final_backend_progress_releases_loading_runtime():
    result = run_node(
        mixin_runtime_script(
            "ui/src/mixins/cleanupMixin.js",
            """
            const events = [];
            const component = createComponent({
              cleanupLoading: true,
              cleanupProgress: { running: true },
              callDsmApi: async () => ({ success: true, data: { running: false, finished: true } }),
              stopCleanupProgressPolling: () => events.push('stop'),
            });

            await component.fetchCleanupProgress();

            assert.strictEqual(component.cleanupLoading, false);
            assert.deepStrictEqual(events, ['stop']);
            console.log(JSON.stringify({ loading: component.cleanupLoading, events }));
            """
        )
    )

    assert result == {"loading": False, "events": ["stop"]}


def test_cleanup_runtime_action_overrides_face_match_recognition_selection_runtime():
    result = run_node(
        mixin_runtime_script(
            "ui/src/mixins/cleanupMixin.js",
            """
            const component = createComponent({
              selectedCleanupAction: 'normalize_names',
              cleanupRuntimeAction: 'normalize_names',
              selectedFaceMatchingAction: 'recognition_analyze_unknown_faces',
            });

            assert.strictEqual(component.faceMatchRecognitionActionSelected, true);
            assert.strictEqual(component.activeCleanupAction, 'normalize_names');
            assert.strictEqual(component.selectedRecognitionAction, 'normalize_names');
            assert.strictEqual(component.isRecognitionCleanupAction, false);
            console.log(JSON.stringify({
              selectedRecognitionAction: component.selectedRecognitionAction,
              isRecognitionCleanupAction: component.isRecognitionCleanupAction,
            }));
            """
        )
    )

    assert result == {
        "selectedRecognitionAction": "normalize_names",
        "isRecognitionCleanupAction": False,
    }


def test_file_analysis_poll_error_keeps_backend_owned_running_state_runtime():
    result = run_node(
        mixin_runtime_script(
            "ui/src/mixins/statusMixin.js",
            """
            const events = [];
            const component = createComponent({
              fileAnalysisProgress: { running: true, finished: false },
              callFileAnalysisApi: async () => { throw new Error('network status 0'); },
              stopFileAnalysisProgressPolling: () => events.push('stop'),
            });

            await component.fetchFileAnalysisProgress();

            assert.strictEqual(component.fileAnalysisProgress.running, true);
            assert.match(component.fileAnalysisProgress.message, /network status 0/);
            assert.deepStrictEqual(events, []);
            console.log(JSON.stringify({ running: component.fileAnalysisProgress.running, events }));
            """
        )
    )

    assert result == {"running": True, "events": []}


def test_file_analysis_final_backend_progress_stops_polling_runtime():
    result = run_node(
        mixin_runtime_script(
            "ui/src/mixins/statusMixin.js",
            """
            const events = [];
            const component = createComponent({
              fileAnalysisProgress: { running: true, finished: false },
              callFileAnalysisApi: async () => ({ success: true, data: { running: false, finished: true } }),
              stopFileAnalysisProgressPolling: () => events.push('stop'),
            });

            await component.fetchFileAnalysisProgress();

            assert.strictEqual(component.fileAnalysisProgress.running, false);
            assert.deepStrictEqual(events, ['stop']);
            console.log(JSON.stringify({ running: component.fileAnalysisProgress.running, events }));
            """
        )
    )

    assert result == {"running": False, "events": ["stop"]}
