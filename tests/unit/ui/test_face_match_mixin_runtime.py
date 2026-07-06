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


def face_match_runtime_script(test_body: str) -> str:
    return textwrap.dedent(
        f"""
        const fs = require('fs');
        const vm = require('vm');
        const assert = require('assert');

        const source = fs.readFileSync('ui/src/mixins/faceMatchMixin.js', 'utf8')
          .replace('export default', 'module.exports =');
        const sandbox = {{ module: {{ exports: {{}} }}, exports: {{}} }};
        vm.runInNewContext(source, sandbox, {{ filename: 'faceMatchMixin.js' }});
        const mixin = sandbox.module.exports;

        function createComponent(overrides = {{}}) {{
          const state = mixin.data.call({{}});
          const component = Object.assign({{}}, state);
          for (const [name, fn] of Object.entries(mixin.methods || {{}})) {{
            component[name] = fn.bind(component);
          }}
          Object.assign(component, overrides);
          for (const [name, getter] of Object.entries(mixin.computed || {{}})) {{
            Object.defineProperty(component, name, {{
              get() {{ return getter.call(component); }},
              configurable: true,
            }});
          }}
          component.$avt = (key, fallback, params) => {{
            if (!params) return fallback || key;
            return String(fallback || key).replace(/\\{{([^}}]+)\\}}/g, (_, token) => String(params[token] ?? ''));
          }};
          component.getResponseData = component.getResponseData || ((data) => (
            data && typeof data.data === 'object' && data.data ? data.data : {{}}
          ));
          component.getResponseDataObject = component.getResponseDataObject || ((data, key) => {{
            const root = component.getResponseData(data);
            return root && typeof root[key] === 'object' && root[key] ? root[key] : {{}};
          }});
          component.getBackendImagePreviewUrl = component.getBackendImagePreviewUrl || ((path) => {{
            const normalized = String(path || '').trim();
            return normalized ? `/webman/3rdparty/AV_ImgData/index.cgi/api/file_image?path=${{encodeURIComponent(normalized)}}` : '';
          }});
          component.isBrowserImageCompatiblePath = component.isBrowserImageCompatiblePath || ((path) => {{
            const match = String(path || '').trim().toLowerCase().match(/\\.([a-z0-9]+)(?:[?#].*)?$/);
            const extension = match ? match[1] : '';
            return ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg', 'avif'].indexOf(extension) >= 0;
          }});
          component.output = '';
          component.stopFaceMatchProgressPolling = component.stopFaceMatchProgressPolling || (() => {{}});
          component.resetFaceMatchSelectionState = component.resetFaceMatchSelectionState || (() => {{}});
          component.clearFaceMatchSuggestions = component.clearFaceMatchSuggestions || (() => {{}});
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


def test_findings_status_fetch_error_preserves_previous_availability_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            const component = createComponent({
              faceMatchFindingsStatus: { status: 'running', count: 1528, save_only: true },
              callFileAnalysisApi: async () => { throw new Error('network status 0'); },
            });

            await component.fetchFaceMatchFindingsStatus();

            assert.strictEqual(component.faceMatchFindingsStatus.count, 1528);
            assert.strictEqual(component.hasFaceMatchStoredFindings, true);
            console.log(JSON.stringify({ count: component.faceMatchFindingsStatus.count }));
            """
        )
    )

    assert result["count"] == 1528


def test_stored_findings_availability_is_bound_to_selected_action_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            const component = createComponent({
              selectedFaceMatchingAction: 'search_photo_face_in_file',
              faceMatchFindingsStatus: {
                action: 'mark_missing_photos_faces',
                requested_action: 'search_photo_face_in_file',
                count: 8,
              },
            });

            assert.strictEqual(component.hasFaceMatchStoredFindings, false);

            component.selectedFaceMatchingAction = 'mark_missing_photos_faces';
            assert.strictEqual(component.hasFaceMatchStoredFindings, true);
            console.log(JSON.stringify({ hasFindings: component.hasFaceMatchStoredFindings }));
            """
        )
    )

    assert result == {"hasFindings": True}


def test_stored_findings_status_count_is_not_review_progress_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            const component = createComponent({
              selectedFaceMatchingAction: 'search_photo_face_in_file',
              faceMatchUseStoredFindings: true,
              faceMatchFindingsStatus: {
                action: 'search_photo_face_in_file',
                requested_action: 'search_photo_face_in_file',
                count: 1050,
              },
              faceMatchFindingEntries: [],
              faceMatchFindingEntriesTotal: 0,
            });

            assert.strictEqual(component.hasFaceMatchStoredFindings, true);
            assert.strictEqual(component.faceMatchShowStoredFindingsProgress, false);
            assert.strictEqual(component.faceMatchStoredFindingsTotal, 0);
            assert.strictEqual(component.faceMatchStoredFindingsChecked, 0);

            component.faceMatchFindingEntries = Array.from({ length: 1050 }, (_, index) => ({ id: index + 1 }));
            component.faceMatchFindingEntriesTotal = 1050;

            assert.strictEqual(component.faceMatchShowStoredFindingsProgress, true);
            assert.strictEqual(component.faceMatchStoredFindingsTotal, 1050);
            assert.strictEqual(component.faceMatchStoredFindingsChecked, 1);
            console.log(JSON.stringify({
              available: component.hasFaceMatchStoredFindings,
              checked: component.faceMatchStoredFindingsChecked,
              total: component.faceMatchStoredFindingsTotal,
            }));
            """
        )
    )

    assert result == {"available": True, "checked": 1, "total": 1050}


def test_switching_face_match_action_disables_foreign_stored_findings_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            const events = [];
            const component = createComponent({
              selectedFaceMatchingAction: 'mark_missing_photos_faces',
              faceMatchUseStoredFindings: true,
              faceMatchFindingEntries: [{ id: 1 }],
              faceMatchFindingsStatus: {
                action: 'mark_missing_photos_faces',
                count: 1,
              },
              resetFaceMatchFindingsReview: () => {
                events.push('reset-review');
                component.faceMatchFindingEntries = [];
              },
              fetchFaceMatchFindingsStatus: async () => events.push('fetch-status'),
            });

            mixin.watch.selectedFaceMatchingAction.call(component, 'search_photo_face_in_file');

            assert.strictEqual(component.faceMatchUseStoredFindings, false);
            assert.deepStrictEqual(component.faceMatchFindingEntries, []);
            assert.deepStrictEqual(events, ['reset-review', 'fetch-status']);
            console.log(JSON.stringify({ useStored: component.faceMatchUseStoredFindings, events }));
            """
        )
    )

    assert result == {"useStored": False, "events": ["reset-review", "fetch-status"]}


def test_findings_status_zero_count_still_disables_active_review_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            const component = createComponent({
              faceMatchUseStoredFindings: true,
              faceMatchFindingsStatus: { status: 'running', count: 5 },
              faceMatchFindingEntries: [{ id: 1 }],
              callFileAnalysisApi: async () => ({ success: true, data: { status: 'finished', count: 0 } }),
            });

            await component.fetchFaceMatchFindingsStatus();

            assert.strictEqual(component.faceMatchUseStoredFindings, false);
            assert.strictEqual(component.faceMatchFindingEntries.length, 0);
            console.log(JSON.stringify({ useStored: component.faceMatchUseStoredFindings }));
            """
        )
    )

    assert result["useStored"] is False


def test_load_stored_findings_sends_selected_source_action_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            let requestBody = null;
            const component = createComponent({
              selectedFaceMatchingAction: 'mark_missing_photos_faces',
              callFileAnalysisApi: async (_path, body) => {
                requestBody = body;
                return {
                  success: true,
                  data: {
                    face_matches: {
                      action: 'mark_missing_photos_faces',
                      requested_action: 'mark_missing_photos_faces',
                      count: 0,
                      entries: [],
                    },
                  },
                };
              },
            });

            await component.loadStoredFaceMatchFindings();

            assert.strictEqual(requestBody.action, 'load_photo_face_match_findings');
            assert.strictEqual(requestBody.findings_action, 'mark_missing_photos_faces');
            assert.strictEqual(component.faceMatchUseStoredFindings, false);
            console.log(JSON.stringify({ requestBody, useStored: component.faceMatchUseStoredFindings }));
            """
        )
    )

    assert result["requestBody"]["findings_action"] == "mark_missing_photos_faces"
    assert result["useStored"] is False


def test_primary_button_loads_stored_findings_when_enabled_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            const events = [];
            const component = createComponent({
              selectedFaceMatchingAction: 'mark_missing_photos_faces',
              faceMatchUseStoredFindings: true,
              faceMatchFindingsStatus: {
                action: 'mark_missing_photos_faces',
                requested_action: 'mark_missing_photos_faces',
                count: 1,
              },
              loadStoredFaceMatchFindings: async () => events.push('load-stored'),
              startFaceMatchingAction: async () => events.push('start-scan'),
            });

            await component.handlePrimaryFaceMatchButton();

            assert.deepStrictEqual(events, ['load-stored']);
            assert.strictEqual(component.faceMatchLoading, false);
            console.log(JSON.stringify({ events, loading: component.faceMatchLoading }));
            """
        )
    )

    assert result == {"events": ["load-stored"], "loading": False}


def test_stored_findings_person_creation_advances_without_full_refresh_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            const events = [];
            const component = createComponent({
              selectedFaceMatchingAction: 'search_photo_face_in_file',
              faceMatchUseStoredFindings: true,
              faceMatchAutoAssignKnown: false,
              faceMatchEditableName: 'Sven',
              faceMatchResult: {
                action: 'search_photo_face_in_file',
                face: { face_id: 149661 },
                image_path: '/volume1/photo/sven.jpg',
              },
              resolveFaceMatchNameMappingPreference: async () => ({
                saveMapping: false,
                sourceName: 'Sven',
              }),
              callDsmApi: async (_path, body) => {
                events.push({ type: 'create', body });
                return { success: true, data: { person_id: 40309 } };
              },
              loadStoredFaceMatchFindings: async (options) => {
                events.push({ type: 'reload', auto: component.faceMatchAutoAssignKnown, options });
              },
              advanceFaceMatchFindingsAfterTransfer: async () => {
                events.push({ type: 'local-advance' });
              },
            });

            await component.createFaceMatchPerson();

            assert.strictEqual(events.length, 2);
            assert.strictEqual(events[0].type, 'create');
            assert.strictEqual(events[0].body.person_name, 'Sven');
            assert.strictEqual(events[1].type, 'local-advance');
            console.log(JSON.stringify({ events }));
            """
        )
    )

    assert result == {
        "events": [
            {
                "type": "create",
                    "body": {
                        "face_id": 149661,
                        "image_path": "/volume1/photo/sven.jpg",
                        "person_name": "Sven",
                        "save_mapping": False,
                        "source_name": "Sven",
                },
            },
            {"type": "local-advance"},
        ],
    }


def test_stored_findings_person_creation_auto_assign_reloads_without_refresh_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            const events = [];
            const component = createComponent({
              selectedFaceMatchingAction: 'search_photo_face_in_file',
              faceMatchUseStoredFindings: true,
              faceMatchAutoAssignKnown: true,
              faceMatchEditableName: 'Sven',
              faceMatchResult: {
                action: 'search_photo_face_in_file',
                face: { face_id: 149661 },
                image_path: '/volume1/photo/sven.jpg',
              },
              resolveFaceMatchNameMappingPreference: async () => ({
                saveMapping: false,
                sourceName: 'Sven',
              }),
              callDsmApi: async (_path, body) => {
                events.push({ type: 'create', body });
                return { success: true, data: { person_id: 40309 } };
              },
              loadStoredFaceMatchFindings: async (options) => {
                events.push({ type: 'reload', auto: component.faceMatchAutoAssignKnown, options });
              },
              advanceFaceMatchFindingsAfterTransfer: async () => {
                events.push({ type: 'local-advance' });
              },
            });

            await component.createFaceMatchPerson();

            assert.strictEqual(events.length, 2);
            assert.strictEqual(events[0].type, 'create');
            assert.strictEqual(events[1].type, 'reload');
            assert.strictEqual(events[1].auto, true);
            assert.deepStrictEqual(events[1].options, undefined);
            console.log(JSON.stringify({ events }));
            """
        )
    )

    assert result == {
        "events": [
            {
                "type": "create",
                    "body": {
                        "face_id": 149661,
                        "image_path": "/volume1/photo/sven.jpg",
                        "person_name": "Sven",
                        "save_mapping": False,
                        "source_name": "Sven",
                },
            },
            {"type": "reload", "auto": True},
        ],
    }


def test_saved_mapping_is_applied_to_next_loaded_finding_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            const targetPerson = { id: 91, name: 'Person Target' };
            const first = {
              image_path: '/volume1/photo/first.jpg',
              source_name: 'Person Legacy',
              metadata_face: { name: 'Person Legacy' },
            };
            const second = {
              image_path: '/volume1/photo/second.jpg',
              source_name: 'Person Legacy',
              metadata_face: { name: 'Person Legacy' },
              matched_person: null,
              matched_person_id: null,
              name_mapping: null,
            };
            const unrelated = {
              image_path: '/volume1/photo/third.jpg',
              source_name: 'Other Person',
              metadata_face: { name: 'Other Person' },
              matched_person: null,
              name_mapping: null,
            };
            const component = createComponent({
              faceMatchFindingEntries: [first, second, unrelated],
            });

            component.applySavedFaceMatchNameMapping(
              { success: true, data: { mapping_saved: true } },
              { saveMapping: true, sourceName: 'Person Legacy' },
              'Person Target',
              targetPerson
            );

            assert.strictEqual(component.faceMatchFindingEntries[1].name_mapping.source_name, 'Person Legacy');
            assert.strictEqual(component.faceMatchFindingEntries[1].name_mapping.target_name, 'Person Target');
            assert.strictEqual(component.faceMatchFindingEntries[1].matched_person.id, 91);
            assert.strictEqual(component.faceMatchFindingEntries[1].matched_person_id, 91);
            assert.strictEqual(component.faceMatchFindingEntries[2], unrelated);
            console.log(JSON.stringify({
              mapping: component.faceMatchFindingEntries[1].name_mapping,
              personId: component.faceMatchFindingEntries[1].matched_person_id,
            }));
            """
        )
    )

    assert result == {
        "mapping": {
            "source_name": "Person Legacy",
            "target_name": "Person Target",
        },
        "personId": 91,
    }


def test_stored_findings_auto_apply_polls_progress_while_request_is_running_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            const events = [];
            const component = createComponent({
              selectedFaceMatchingAction: 'search_photo_face_in_file',
              faceMatchAutoAssignKnown: true,
              startFaceMatchProgressPolling: () => events.push('start-polling'),
              stopFaceMatchProgressPolling: () => events.push('stop-polling'),
              fetchFaceMatchingProgress: async () => events.push('fetch-progress'),
              callFileAnalysisApi: async (_path, body) => {
                events.push({ type: 'request', body });
                return {
                  success: true,
                  data: {
                    face_matches: {
                      action: 'search_photo_face_in_file',
                      requested_action: 'search_photo_face_in_file',
                      count: 1,
                      entries: [{ id: 1 }],
                    },
                  },
                };
              },
            });

            await component.loadStoredFaceMatchFindings({ refresh: true });

            assert.strictEqual(JSON.stringify(events), JSON.stringify([
              'start-polling',
              {
                type: 'request',
                body: {
                  action: 'load_photo_face_match_findings',
                  findings_action: 'search_photo_face_in_file',
                  auto: true,
                  refresh: true,
                },
              },
              'fetch-progress',
              'stop-polling',
            ]));
            assert.strictEqual(component.faceMatchLoading, false);
            console.log(JSON.stringify({ events, loading: component.faceMatchLoading }));
            """
        )
    )

    assert result["loading"] is False


def test_stored_findings_status_uses_active_finding_action_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            let requestBody = null;
            const component = createComponent({
              selectedFaceMatchingAction: 'search_photo_face_in_file',
              faceMatchUseStoredFindings: true,
              faceMatchFindingEntries: [{ id: 1 }],
              faceMatchResult: {
                id: 1,
                action: 'search_file_face_in_sources',
              },
              callFileAnalysisApi: async (_path, body) => {
                requestBody = body;
                return {
                  success: true,
                  data: {
                    action: 'search_file_face_in_sources',
                    requested_action: 'search_file_face_in_sources',
                    count: 55,
                  },
                };
              },
            });

            await component.fetchFaceMatchFindingsStatus();

            assert.strictEqual(requestBody.action, 'search_file_face_in_sources');
            assert.strictEqual(component.faceMatchUseStoredFindings, true);
            assert.strictEqual(component.hasFaceMatchStoredFindings, true);
            console.log(JSON.stringify({ action: requestBody.action, count: component.faceMatchFindingsStatus.count }));
            """
        )
    )

    assert result == {"action": "search_file_face_in_sources", "count": 55}


def test_load_stored_findings_prefers_status_action_during_review_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            let requestBody = null;
            const component = createComponent({
              selectedFaceMatchingAction: 'search_photo_face_in_file',
              faceMatchUseStoredFindings: true,
              faceMatchFindingsStatus: {
                action: 'search_file_face_in_sources',
                requested_action: 'search_photo_face_in_file',
                count: 55,
              },
              callFileAnalysisApi: async (_path, body) => {
                requestBody = body;
                return {
                  success: true,
                  data: {
                    face_matches: {
                      action: 'search_file_face_in_sources',
                      requested_action: 'search_file_face_in_sources',
                      count: 1,
                      entries: [{ id: 1, action: 'search_file_face_in_sources' }],
                    },
                  },
                };
              },
            });

            await component.loadStoredFaceMatchFindings();

            assert.strictEqual(requestBody.findings_action, 'search_file_face_in_sources');
            assert.strictEqual(component.faceMatchResult.action, 'search_file_face_in_sources');
            console.log(JSON.stringify({ findingsAction: requestBody.findings_action, resultAction: component.faceMatchResult.action }));
            """
        )
    )

    assert result == {
        "findingsAction": "search_file_face_in_sources",
        "resultAction": "search_file_face_in_sources",
    }


def test_reloaded_stored_findings_keep_original_review_total_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            const responses = [
              { count: 114, transferred_count: 0, entries: Array.from({ length: 114 }, (_, index) => ({ id: index + 1 })) },
              { count: 113, transferred_count: 1, entries: Array.from({ length: 113 }, (_, index) => ({ id: index + 2 })) },
            ];
            const component = createComponent({
              selectedFaceMatchingAction: 'search_file_face_in_sources',
              callFileAnalysisApi: async () => ({
                success: true,
                data: {
                  face_matches: {
                    action: 'search_file_face_in_sources',
                    requested_action: 'search_file_face_in_sources',
                    save_only: true,
                    status: 'finished',
                    ...responses.shift(),
                  },
                },
              }),
            });

            await component.loadStoredFaceMatchFindings();
            assert.strictEqual(component.faceMatchFindingEntriesTotal, 114);
            assert.strictEqual(component.faceMatchStoredFindingsChecked, 1);

            await component.loadStoredFaceMatchFindings();
            assert.strictEqual(component.faceMatchFindingEntriesTotal, 114);
            assert.strictEqual(component.faceMatchStoredFindingsCompletedCount, 1);
            assert.strictEqual(component.faceMatchStoredFindingsChecked, 2);
            console.log(JSON.stringify({
              total: component.faceMatchFindingEntriesTotal,
              completed: component.faceMatchStoredFindingsCompletedCount,
              checked: component.faceMatchStoredFindingsChecked,
            }));
            """
        )
    )

    assert result == {"total": 114, "completed": 1, "checked": 2}


def test_stored_findings_next_is_not_overwritten_by_stale_scan_progress_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            const entries = [
              { id: 1, action: 'search_file_face_in_sources', image_path: '/volume1/photo/one.jpg' },
              { id: 2, action: 'search_file_face_in_sources', image_path: '/volume1/photo/two.jpg' },
            ];
            const component = createComponent({
              selectedFaceMatchingAction: 'search_photo_face_in_file',
              faceMatchUseStoredFindings: true,
              faceMatchFindingEntries: entries,
              faceMatchFindingEntriesTotal: 2,
              faceMatchFindingIndex: 0,
              faceMatchResult: entries[0],
            });

            await component.loadNextFaceMatch();
            assert.strictEqual(component.faceMatchFindingIndex, 0);
            assert.strictEqual(component.faceMatchResult.id, 2);
            assert.strictEqual(component.faceMatchFindingEntries.length, 1);

            const applied = component.applyFaceMatchingProgress({
              running: false,
              action: 'search_file_face_in_sources',
              status: {
                schema_version: 1,
                mode: 'scan',
                phase: 'finished',
              },
              result: entries[0],
            });

            assert.strictEqual(applied, true);
            assert.strictEqual(component.faceMatchFindingIndex, 0);
            assert.strictEqual(component.faceMatchResult.id, 2);
            assert.match(component.faceMatchProgress.message, /List entry 2 of 2/);
            console.log(JSON.stringify({
              index: component.faceMatchFindingIndex,
              resultId: component.faceMatchResult.id,
              entries: component.faceMatchFindingEntries.length,
              message: component.faceMatchProgress.message,
            }));
            """
        )
    )

    assert result == {
        "index": 0,
        "resultId": 2,
        "entries": 1,
        "message": "List entry 2 of 2.",
    }


def test_finished_face_match_progress_result_is_renderable_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            const component = createComponent({
              selectedFaceMatchingAction: 'search_photo_face_in_file',
            });

            const applied = component.applyFaceMatchingProgress({
              running: false,
              finished: true,
              stale: true,
              action: 'search_photo_face_in_file',
              message_key: 'face_match:result_named_match_with_id',
              message_params: { id: 27353 },
              findings_count: 1,
              result: {
                searched: true,
                metadata_face: {
                  name: 'Person Candidate',
                  source: 'embedded_xmp_parsed',
                  source_format: 'ACD',
                },
                match: { score: 1 },
                matched_person: { id: 27353, name: 'Person Candidate' },
              },
            });

            assert.strictEqual(applied, true);
            assert.strictEqual(component.faceMatchResultSummary.found, true);
            assert.strictEqual(component.faceMatchResultSummary.name, 'Person Candidate');
            assert.strictEqual(component.faceMatchResultSummary.photosPersonId, 27353);
            console.log(JSON.stringify({
              found: component.faceMatchResultSummary.found,
              name: component.faceMatchResultSummary.name,
              photosPersonId: component.faceMatchResultSummary.photosPersonId,
            }));
            """
        )
    )

    assert result == {
        "found": True,
        "name": "Person Candidate",
        "photosPersonId": 27353,
    }


def test_skipped_stored_finding_stays_filtered_after_reload_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            const entries = [
              { id: 1, action: 'search_file_face_in_sources', image_path: '/volume1/photo/one.jpg' },
              { id: 2, action: 'search_file_face_in_sources', image_path: '/volume1/photo/two.jpg' },
            ];
            let loads = 0;
            const component = createComponent({
              selectedFaceMatchingAction: 'search_file_face_in_sources',
              faceMatchUseStoredFindings: true,
              faceMatchFindingEntries: entries.slice(),
              faceMatchFindingEntriesTotal: 2,
              faceMatchFindingIndex: 0,
              faceMatchResult: entries[0],
              callFileAnalysisApi: async () => {
                loads += 1;
                return {
                  success: true,
                  data: {
                    face_matches: {
                      action: 'search_file_face_in_sources',
                      requested_action: 'search_file_face_in_sources',
                      count: 2,
                      transferred_count: 0,
                      entries: entries.slice(),
                    },
                  },
                };
              },
            });

            await component.loadNextFaceMatch();
            assert.strictEqual(component.faceMatchResult.id, 2);

            await component.loadStoredFaceMatchFindings();

            assert.strictEqual(loads, 1);
            assert.strictEqual(component.faceMatchFindingEntries.length, 1);
            assert.strictEqual(component.faceMatchResult.id, 2);
            assert.strictEqual(component.faceMatchStoredFindingsChecked, 2);
            console.log(JSON.stringify({
              loads,
              entries: component.faceMatchFindingEntries.length,
              resultId: component.faceMatchResult.id,
              checked: component.faceMatchStoredFindingsChecked,
            }));
            """
        )
    )

    assert result == {
        "loads": 1,
        "entries": 1,
        "resultId": 2,
        "checked": 2,
    }


def test_file_source_face_match_titles_show_source_target_and_image_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            const component = createComponent({
              selectedFaceMatchingAction: 'search_file_face_in_sources',
              faceMatchUseStoredFindings: true,
              faceMatchResult: {
                action: 'search_file_face_in_sources',
                image_path: '/volume1/photo/Familie/Kaire/IMG_0001.JPG',
                source_face: { name: 'Kaire Vilippus' },
                metadata_face: { name: '' },
              },
            });

            assert.strictEqual(component.faceMatchLeftTitle, 'Name source');
            assert.strictEqual(component.faceMatchRightTitle, 'File marking to name');
            assert.strictEqual(component.faceMatchImageContextTitle, 'File: IMG_0001.JPG');
            assert.strictEqual(component.faceMatchImageContextPath, '/volume1/photo/Familie/Kaire/IMG_0001.JPG');
            console.log(JSON.stringify({
              left: component.faceMatchLeftTitle,
              right: component.faceMatchRightTitle,
              image: component.faceMatchImageContextTitle,
              path: component.faceMatchImageContextPath,
            }));
            """
        )
    )

    assert result == {
        "left": "Name source",
        "right": "File marking to name",
        "image": "File: IMG_0001.JPG",
        "path": "/volume1/photo/Familie/Kaire/IMG_0001.JPG",
    }


def test_missing_photos_face_has_no_marker_on_photos_side_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            const metadataFace = { name: 'Old Name', x: 0.5, y: 0.5, w: 0.2, h: 0.2 };
            const component = createComponent({
              selectedFaceMatchingAction: 'mark_missing_photos_faces',
              personDataToLeftIconUrl: 'person_data_to_left.png',
              personDataToRightIconUrl: 'person_data_to_right.png',
              faceMatchResult: {
                action: 'mark_missing_photos_faces',
                image_path: '/volume1/photo/test.jpg',
                metadata_face: metadataFace,
                source_face: metadataFace,
                add_new_faces_to_photos: true,
              },
            });

            assert.deepStrictEqual(component.getLeftFaceMatchFace(), metadataFace);
            assert.strictEqual(component.getRightFaceMatchFace(), null);
            assert.strictEqual(component.faceMatchCanDeleteMetadataFace, true);
            assert.strictEqual(component.faceMatchTransferIconUrl, 'person_data_to_right.png');
            console.log(JSON.stringify({
              right: component.getRightFaceMatchFace(),
              canDelete: component.faceMatchCanDeleteMetadataFace,
              transferIcon: component.faceMatchTransferIconUrl,
            }));
            """
        )
    )

    assert result == {
        "right": None,
        "canDelete": True,
        "transferIcon": "person_data_to_right.png",
    }


def test_different_photos_name_prompts_for_file_name_update_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            const component = createComponent({
              selectedFaceMatchingAction: 'mark_missing_photos_faces',
              faceMatchResult: {
                action: 'mark_missing_photos_faces',
                image_path: '/volume1/photo/test.jpg',
                metadata_face: { name: 'Old Name' },
                add_new_faces_to_photos: true,
              },
            });

            const pending = component.confirmMetadataNameUpdate('New Name');
            assert.strictEqual(component.metadataNameConfirm.visible, true);
            assert.match(component.metadataNameConfirm.message, /Old Name/);
            assert.match(component.metadataNameConfirm.message, /New Name/);
            component.resolveMetadataNameConfirm(true);
            const update = await pending;
            assert.strictEqual(update, true);
            console.log(JSON.stringify({ update }));
            """
        )
    )

    assert result == {"update": True}


def test_use_stored_findings_and_save_only_watchers_are_mutually_exclusive_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            const events = [];
            const component = createComponent({
              faceMatchSaveOnly: true,
              faceMatchUseStoredFindings: false,
              faceMatchFindingsStatus: { action: 'search_photo_face_in_file', count: 1 },
              resetFaceMatchFindingsReview: () => events.push('reset-review'),
            });

            mixin.watch.faceMatchUseStoredFindings.call(component, true);

            assert.strictEqual(component.faceMatchSaveOnly, false);
            assert.deepStrictEqual(events, []);

            component.faceMatchUseStoredFindings = true;
            mixin.watch.faceMatchSaveOnly.call(component, true);

            assert.strictEqual(component.faceMatchUseStoredFindings, false);
            mixin.watch.faceMatchUseStoredFindings.call(component, false);
            assert.deepStrictEqual(events, ['reset-review']);
            console.log(JSON.stringify({ saveOnly: component.faceMatchSaveOnly, useStored: component.faceMatchUseStoredFindings, events }));
            """
        )
    )

    assert result == {
        "saveOnly": False,
        "useStored": False,
        "events": ["reset-review"],
    }


def test_stored_findings_mutation_error_reloads_backend_state_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            let reloads = 0;
            const component = createComponent({
              faceMatchUseStoredFindings: true,
              loadStoredFaceMatchFindings: async () => {
                reloads += 1;
                component.faceMatchFindingEntries = [{ id: 2 }];
                component.faceMatchFindingsStatus = { count: 1 };
              },
            });

            await component.reconcileStoredFaceMatchFindingsAfterMutationError(new Error('Backend request timed out.'));

            assert.strictEqual(reloads, 1);
            assert.strictEqual(component.faceMatchFindingsStatus.count, 1);
            assert.strictEqual(component.faceMatchFindingEntries.length, 1);
            assert.match(component.output, /Backend request timed out/);
            console.log(JSON.stringify({ reloads, count: component.faceMatchFindingsStatus.count }));
            """
        )
    )

    assert result == {"reloads": 1, "count": 1}


def test_live_start_does_not_poll_until_start_response_is_applied_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            const events = [];
            const component = createComponent({
              selectedFaceMatchingAction: 'search_photo_face_in_file',
              callDsmApi: async () => {
                events.push('action-called');
                assert.deepStrictEqual(events, ['stop-polling', 'action-called']);
                return { success: true, data: { face_matches: { running: true, action: 'search_photo_face_in_file' } } };
              },
              stopFaceMatchProgressPolling: () => events.push('stop-polling'),
              startFaceMatchProgressPolling: () => events.push('start-polling'),
              applyFaceMatchingProgress: () => {
                events.push('apply-progress');
                return true;
              },
              fetchFaceMatchFindingsStatus: async () => events.push('fetch-findings-status'),
              syncFaceMatchTransferredCountFromProgress: () => events.push('sync-count'),
            });

            await component.startFaceMatchingAction();

            assert.deepStrictEqual(events, [
              'stop-polling',
              'action-called',
              'apply-progress',
              'start-polling',
              'fetch-findings-status',
              'sync-count',
            ]);
            console.log(JSON.stringify({ events }));
            """
        )
    )

    assert result["events"][0:4] == [
        "stop-polling",
        "action-called",
        "apply-progress",
        "start-polling",
    ]


def test_auto_assign_known_is_not_supported_for_insightface_actions_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            const events = [];
            const component = createComponent({
              selectedFaceMatchingAction: 'search_photo_face_in_file',
              faceMatchAutoAssignKnown: true,
              fetchFaceMatchFindingsStatus: async () => events.push('findings-status'),
            });

            assert.strictEqual(component.faceMatchSupportsAutoAssignKnown, true);
            component.selectedFaceMatchingAction = 'search_missing_faces_insightface';
            mixin.watch.selectedFaceMatchingAction.call(component, 'search_missing_faces_insightface');

            assert.strictEqual(component.faceMatchSupportsAutoAssignKnown, false);
            assert.strictEqual(component.faceMatchAutoAssignKnown, false);

            component.selectedFaceMatchingAction = 'recognition_analyze_unknown_faces';
            assert.strictEqual(component.faceMatchSupportsAutoAssignKnown, false);
            console.log(JSON.stringify({
              supports: component.faceMatchSupportsAutoAssignKnown,
              autoAssign: component.faceMatchAutoAssignKnown,
              events,
            }));
            """
        )
    )

    assert result == {
        "supports": False,
        "autoAssign": False,
        "events": ["findings-status"],
    }


def test_insightface_missing_face_start_sends_auto_only_for_safe_apply_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            let requestBody = null;
            const component = createComponent({
              selectedFaceMatchingAction: 'search_missing_faces_insightface',
	              faceMatchAutoAssignKnown: true,
	              faceMatchRecognizeMissingInsightFacePersons: true,
	              faceMatchSkipUnknownInsightFacePersons: true,
	              faceMatchAutoApplySafeInsightFacePersons: true,
              insightFaceStatus: {
                native_processors: {
                  FACE_PROCESSOR: {
                    available: true,
                    hot_path_available: true,
                  },
                },
              },
              callDsmApi: async (_path, body) => {
                requestBody = body;
                return {
                  success: true,
                  data: {
                    face_matches: {
                      running: true,
                      action: 'search_missing_faces_insightface',
                    },
                  },
                };
              },
              applyFaceMatchingProgress: () => true,
              fetchFaceMatchFindingsStatus: async () => {},
              syncFaceMatchTransferredCountFromProgress: () => {},
              startFaceMatchProgressPolling: () => {},
              stopFaceMatchProgressPolling: () => {},
            });

            await component.startFaceMatchingAction();

	            assert.strictEqual(requestBody.action, 'search_missing_faces_insightface');
	            assert.strictEqual(requestBody.auto, true);
	            assert.strictEqual(requestBody.recognize_persons, true);
	            assert.strictEqual(requestBody.skip_unknown_persons, true);
            console.log(JSON.stringify({ requestBody }));
            """
        )
    )

    assert result["requestBody"]["action"] == "search_missing_faces_insightface"
    assert result["requestBody"]["auto"] is True
    assert result["requestBody"]["recognize_persons"] is True
    assert result["requestBody"]["skip_unknown_persons"] is True


def test_followup_start_accepts_authoritative_response_with_older_revision_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            const events = [];
            const component = createComponent({
              selectedFaceMatchingAction: 'search_photo_face_in_file',
              faceMatchProgress: {
                operation_id: 'face_match-existing',
                revision: 12,
                running: false,
                finished: true,
              },
              callDsmApi: async () => ({
                success: true,
                data: {
                  face_matches: {
                    operation_id: 'face_match-existing',
                    revision: 11,
                    running: true,
                    finished: false,
                    action: 'search_photo_face_in_file',
                  },
                },
              }),
              startFaceMatchProgressPolling: () => events.push('start-polling'),
              stopFaceMatchProgressPolling: () => events.push('stop-polling'),
              fetchFaceMatchFindingsStatus: async () => events.push('fetch-findings-status'),
            });

            await component.startFaceMatchingAction({ resetSkippedFaceIds: false });

            assert.strictEqual(component.faceMatchProgress.running, true);
            assert.strictEqual(component.faceMatchProgress.revision, 11);
            assert.deepStrictEqual(events, [
              'stop-polling',
              'start-polling',
              'fetch-findings-status',
            ]);
            console.log(JSON.stringify({
              running: component.faceMatchProgress.running,
              revision: component.faceMatchProgress.revision,
              events,
            }));
            """
        )
    )

    assert result == {
        "running": True,
        "revision": 11,
        "events": [
            "stop-polling",
            "start-polling",
            "fetch-findings-status",
        ],
    }


def test_unknown_face_progress_counts_stay_monotonic_across_followup_scan_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            const component = createComponent({
              selectedFaceMatchingAction: 'search_photo_face_in_file',
              faceMatchProgressBase: {
                persons_read: 42,
                images_read: 0,
                faces_read: 0,
                target_faces_read: 0,
                metadata_faces_read: 0,
              },
              faceMatchProgress: {
                persons_read: 1,
                persons_total: 10,
              },
            });

            assert.strictEqual(component.faceMatchDisplayedProgress.persons_read, 43);
            assert.strictEqual(component.faceMatchPersonsChecked, 43);
            assert.strictEqual(component.faceMatchPersonsTotal, 52);
            console.log(JSON.stringify({
              checked: component.faceMatchPersonsChecked,
              total: component.faceMatchPersonsTotal,
            }));
            """
        )
    )

    assert result == {"checked": 43, "total": 52}


def test_primary_button_uses_backend_running_progress_as_stop_state_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            const component = createComponent({
              faceMatchLoading: false,
              faceMatchProgress: {
                running: true,
                finished: false,
                status: {
                  schema_version: 1,
                  operation: 'face_match',
                  mode: 'scan',
                  phase: 'running',
                },
              },
            });

            assert.strictEqual(component.faceMatchPrimaryButtonLabel, 'Stop');
            assert.strictEqual(component.faceMatchInteractionDisabled, true);
            console.log(JSON.stringify({
              label: component.faceMatchPrimaryButtonLabel,
              disabled: component.faceMatchInteractionDisabled,
            }));
            """
        )
    )

    assert result == {"label": "Stop", "disabled": True}


def test_primary_button_uses_restart_for_paused_file_search_with_stored_findings_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            const component = createComponent({
              selectedFaceMatchingAction: 'search_photo_face_in_file',
              faceMatchSaveOnly: false,
              faceMatchUseStoredFindings: false,
              faceMatchFindingsStatus: {
                action: 'search_photo_face_in_file',
                count: 3,
              },
              faceMatchResult: { searched: true },
            });

            assert.strictEqual(component.hasFaceMatchStoredFindings, true);
            assert.strictEqual(component.faceMatchCanRestartSavedFileSearch, true);
            assert.strictEqual(component.faceMatchPrimaryButtonLabel, 'Restart');
            console.log(JSON.stringify({ label: component.faceMatchPrimaryButtonLabel }));
            """
        )
    )

    assert result == {"label": "Restart"}


def test_thumbnail_error_switches_to_backend_image_fallback_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            const component = createComponent({
              faceMatchResult: {
                image_path: '/volume1/photo/Familie/Test Bild.jpg',
                image: { id: 115579 },
              },
              getPhotoThumbnailUrl: (image) => `/synofoto/api/v2/t/Thumbnail/get?id=${image.id}`,
            });
            const image = { dataset: {}, src: component.getCurrentFaceMatchImageUrl() };

            component.handleFaceMatchImagePreviewError({ target: image });
            const firstFallback = image.src;
            component.handleFaceMatchImagePreviewError({ target: image });

            assert.strictEqual(
              firstFallback,
              '/webman/3rdparty/AV_ImgData/index.cgi/api/file_image?path=%2Fvolume1%2Fphoto%2FFamilie%2FTest%20Bild.jpg'
            );
            assert.strictEqual(image.src, firstFallback);
            assert.strictEqual(image.dataset.avFallbackApplied, 'true');
            assert.strictEqual(
              image.dataset.avFallbackPrimaryUrl,
              '/synofoto/api/v2/t/Thumbnail/get?id=115579'
            );

            component.faceMatchResult = {
              image_path: '/volume1/photo/Familie/Zweites Bild.jpg',
              image: { id: 115580 },
            };
            image.src = component.getCurrentFaceMatchImageUrl();
            component.handleFaceMatchImagePreviewError({ target: image });

            assert.strictEqual(
              image.src,
              '/webman/3rdparty/AV_ImgData/index.cgi/api/file_image?path=%2Fvolume1%2Fphoto%2FFamilie%2FZweites%20Bild.jpg'
            );
            assert.strictEqual(
              image.dataset.avFallbackPrimaryUrl,
              '/synofoto/api/v2/t/Thumbnail/get?id=115580'
            );
            console.log(JSON.stringify({ fallback: image.src }));
            """
        )
    )

    assert result["fallback"].endswith("Zweites%20Bild.jpg")


def test_heic_preview_uses_backend_image_url_without_synology_thumbnail_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            const component = createComponent({
              faceMatchResult: {
                image_path: '/volume1/photo/Familie/Test Bild.heic',
                image: { id: 115579 },
              },
              getPhotoThumbnailUrl: (image) => `/synofoto/api/v2/t/Thumbnail/get?id=${image.id}`,
            });

            const url = component.getCurrentFaceMatchImageUrl();

            assert.strictEqual(
              url,
              '/webman/3rdparty/AV_ImgData/index.cgi/api/file_image?path=%2Fvolume1%2Fphoto%2FFamilie%2FTest%20Bild.heic'
            );
            console.log(JSON.stringify({ url }));
            """
        )
    )

    assert result["url"].endswith("Test%20Bild.heic")


def test_stale_backend_running_phase_does_not_keep_stop_state_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            const component = createComponent({
              faceMatchLoading: false,
              faceMatchProgress: {
                running: false,
                active: false,
                stale: true,
                finished: false,
                status: {
                  schema_version: 1,
                  operation: 'face_match',
                  mode: 'scan',
                  phase: 'running',
                },
              },
            });

            assert.strictEqual(component.faceMatchPrimaryButtonLabel, 'Start');
            assert.strictEqual(component.faceMatchInteractionDisabled, false);
            console.log(JSON.stringify({
              label: component.faceMatchPrimaryButtonLabel,
              disabled: component.faceMatchInteractionDisabled,
            }));
            """
        )
    )

    assert result == {"label": "Start", "disabled": False}


def test_stale_backend_flat_finished_phase_does_not_keep_stop_state_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            const component = createComponent({
              faceMatchLoading: true,
              faceMatchProgress: {
                running: false,
                active: false,
                stale: true,
                status_phase: 'finished',
              },
            });

            assert.strictEqual(component.faceMatchStatusPhase, 'finished');
            assert.strictEqual(component.faceMatchPrimaryButtonLabel, 'Start');
            assert.strictEqual(component.faceMatchInteractionDisabled, false);
            console.log(JSON.stringify({
              phase: component.faceMatchStatusPhase,
              label: component.faceMatchPrimaryButtonLabel,
              disabled: component.faceMatchInteractionDisabled,
            }));
            """
        )
    )

    assert result == {"phase": "finished", "label": "Start", "disabled": False}


def test_face_match_progress_polling_returns_pending_request_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            let capturedCallback = null;
            const requestPromise = Promise.resolve({ running: true });
            const component = createComponent({
              startNamedPolling: (timerKey, callback, interval, options) => {
                capturedCallback = callback;
                assert.strictEqual(timerKey, 'faceMatchProgressTimer');
                assert.strictEqual(interval, 1000);
                assert.strictEqual(options.skipIfPending, true);
              },
              fetchFaceMatchingProgress: () => requestPromise,
            });

            component.startFaceMatchProgressPolling();

            assert.strictEqual(capturedCallback(), requestPromise);
            console.log(JSON.stringify({ returnsPromise: true }));
            """
        )
    )

    assert result == {"returnsPromise": True}


def test_face_match_progress_fetch_skips_overlap_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            let callCount = 0;
            let resolveRequest = null;
            const component = createComponent({
              callDsmApi: async () => {
                callCount += 1;
                return await new Promise((resolve) => {
                  resolveRequest = resolve;
                });
              },
              fetchFaceMatchFindingsStatus: async () => {},
              stopFaceMatchProgressPolling: () => {},
            });

            const first = component.fetchFaceMatchingProgress();
            const second = await component.fetchFaceMatchingProgress();

            assert.strictEqual(Object.keys(second).length, 0);
            assert.strictEqual(callCount, 1);
            assert.strictEqual(component.faceMatchProgressRequestPending, true);

            resolveRequest({ success: true, data: { running: false, active: false, stale: true, status_phase: 'finished' } });
            const progress = await first;

            assert.strictEqual(progress.status_phase, 'finished');
            assert.strictEqual(component.faceMatchProgressRequestPending, false);
            assert.strictEqual(component.faceMatchLoading, false);
            console.log(JSON.stringify({ callCount, phase: component.faceMatchStatusPhase }));
            """
        )
    )

    assert result == {"callCount": 1, "phase": "finished"}


def test_face_match_start_releases_invalidated_pending_progress_request_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            let progressCallCount = 0;
            let resolveOldProgress = null;
            let resolveNewProgress = null;
            const component = createComponent({
              selectedFaceMatchingAction: 'search_photo_face_in_file',
              callDsmApi: async (path) => {
                if (path.indexOf('face_matching_progress') >= 0) {
                  progressCallCount += 1;
                  return await new Promise((resolve) => {
                    if (progressCallCount === 1) {
                      resolveOldProgress = resolve;
                    } else {
                      resolveNewProgress = resolve;
                    }
                  });
                }
                return {
                  success: true,
                  data: {
                    face_matches: {
                      running: true,
                      active: true,
                      action: 'search_photo_face_in_file',
                      operation_id: 'face_match-new',
                    },
                  },
                };
              },
              fetchFaceMatchFindingsStatus: async () => {},
              startNamedPolling: (_timerKey, callback) => {
                component.pollCallback = callback;
              },
              stopNamedPolling: () => {},
            });

            const oldProgress = component.fetchFaceMatchingProgress();
            assert.strictEqual(component.faceMatchProgressRequestPending, true);

            await component.startFaceMatchingAction();
            assert.strictEqual(component.faceMatchProgressRequestPending, false);

            const newProgress = component.pollCallback();
            assert.strictEqual(progressCallCount, 2);
            assert.strictEqual(component.faceMatchProgressRequestPending, true);

            resolveOldProgress({
              success: true,
              data: {
                running: false,
                active: false,
                stale: true,
                operation_id: 'face_match-old',
                status_phase: 'finished',
              },
            });
            await oldProgress;

            resolveNewProgress({
              success: true,
              data: {
                running: false,
                active: false,
                stale: true,
                operation_id: 'face_match-new',
                status_phase: 'finished',
              },
            });
            await newProgress;

            assert.strictEqual(component.faceMatchProgressRequestPending, false);
            assert.strictEqual(component.faceMatchProgress.operation_id, 'face_match-new');
            console.log(JSON.stringify({
              progressCallCount,
              operationId: component.faceMatchProgress.operation_id,
              pending: component.faceMatchProgressRequestPending,
            }));
            """
        )
    )

    assert result == {
        "progressCallCount": 2,
        "operationId": "face_match-new",
        "pending": False,
    }


def test_primary_button_stops_when_backend_progress_is_running_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            const events = [];
            const component = createComponent({
              faceMatchLoading: false,
              faceMatchProgress: { running: true, finished: false },
              stopFaceMatchingAction: async () => events.push('stop'),
              startFaceMatchingAction: async () => events.push('start'),
            });

            await component.handlePrimaryFaceMatchButton();

            assert.deepStrictEqual(events, ['stop']);
            console.log(JSON.stringify({ events }));
            """
        )
    )

    assert result == {"events": ["stop"]}


def test_primary_button_stops_recognition_face_match_with_face_match_message_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            const calls = [];
            const component = createComponent({
              selectedFaceMatchingAction: 'recognition_analyze_unknown_faces',
              faceMatchRecognitionActionSelected: true,
              cleanupLoading: true,
              syncFaceMatchRecognitionOptions: () => calls.push({ type: 'sync' }),
              stopCleanupRun: async (options) => calls.push({ type: 'stop-cleanup', options }),
              startCleanupRun: async () => calls.push({ type: 'start-cleanup' }),
            });

            await component.handlePrimaryFaceMatchButton();

            assert.strictEqual(calls.length, 2);
            assert.strictEqual(calls[0].type, 'sync');
            assert.strictEqual(calls[1].type, 'stop-cleanup');
            assert.strictEqual(calls[1].options.actionOverride, 'recognition_analyze_unknown_faces');
            assert.strictEqual(calls[1].options.stoppingMessageKey, 'face_match:output_stopping');
            assert.strictEqual(calls[1].options.stoppingMessageDefault, 'Stopping search...');
            console.log(JSON.stringify({ calls }));
            """
        )
    )

    assert result["calls"][1]["options"]["stoppingMessageKey"] == "face_match:output_stopping"


def test_primary_button_stops_recognition_when_cleanup_progress_is_running_runtime():
    result = run_node(
        face_match_runtime_script(
            """
            const calls = [];
            const component = createComponent({
              selectedFaceMatchingAction: 'recognition_analyze_unknown_faces',
              faceMatchRecognitionActionSelected: true,
              cleanupLoading: false,
              cleanupRuntimeAction: 'recognition_analyze_unknown_faces',
              cleanupProgress: {
                action: 'recognition_analyze_unknown_faces',
                running: true,
                status: {
                  phase: 'running',
                },
              },
              syncFaceMatchRecognitionOptions: () => calls.push({ type: 'sync' }),
              stopCleanupRun: async (options) => calls.push({ type: 'stop-cleanup', options }),
              startCleanupRun: async () => calls.push({ type: 'start-cleanup' }),
            });

            assert.strictEqual(component.faceMatchRecognitionCleanupActive, true);
            assert.strictEqual(component.faceMatchPrimaryButtonLabel, 'Stop');

            await component.handlePrimaryFaceMatchButton();

            assert.deepStrictEqual(calls.map((entry) => entry.type), ['sync', 'stop-cleanup']);
            assert.strictEqual(calls[1].options.actionOverride, 'recognition_analyze_unknown_faces');
            console.log(JSON.stringify({
              label: component.faceMatchPrimaryButtonLabel,
              calls,
            }));
            """
        )
    )

    assert result["label"] == "Stop"
    assert [entry["type"] for entry in result["calls"]] == ["sync", "stop-cleanup"]
