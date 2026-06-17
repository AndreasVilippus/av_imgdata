<template>
	<section class="panel">
		<div class="panel-head">
			<div class="sm-section-title">{{ $avt('config:title', 'Configuration') }}</div>
		</div>

		<div class="config-actions config-actions-right">
			<v-button @click="loadConfig" :disabled="loading || saving" style="width: 160px;">
				{{ $avt('config:button_reload', 'Reload') }}
			</v-button>
			<v-button @click="applyDefaults" :disabled="loading || saving" style="width: 160px;">
				{{ $avt('config:button_defaults', 'Defaults') }}
			</v-button>
			<v-button @click="saveConfig" :disabled="loading || saving" style="width: 160px;">
				{{ $avt('config:button_save', 'Save') }}
			</v-button>
		</div>

		<div v-if="message" class="config-message">{{ message }}</div>

		<div v-if="loading" class="config-loading">
			<span class="sm-loader"></span>
			{{ $avt('config:loading', 'Loading configuration...') }}
		</div>

		<div v-else class="config-layout">
			<section class="config-card">
				<div class="sm-section-title">{{ $avt('config:section_runtime', 'Runtime settings') }}</div>
				<div class="config-card-desc">{{ $avt('config:config_path', 'Config path: {path}', { path: configPath || '-' }) }}</div>

				<div class="config-form-grid">
					<label class="config-checkbox">
						<input v-model="configModel.metadata.SCHEMAS.ACD" type="checkbox" :disabled="saving" />
						<span>{{ $avt('config:label_schema_acd', 'Read ACDSee metadata') }}</span>
					</label>

					<label class="config-checkbox">
						<input v-model="configModel.metadata.SCHEMAS.MICROSOFT" type="checkbox" :disabled="saving" />
						<span>{{ $avt('config:label_schema_microsoft', 'Read Microsoft face metadata') }}</span>
					</label>

					<label class="config-checkbox">
						<input v-model="configModel.metadata.SCHEMAS.MWG_REGIONS" type="checkbox" :disabled="saving" />
						<span>{{ $avt('config:label_schema_mwg_regions', 'Read MWG face regions metadata') }}</span>
					</label>

					<label class="config-field">
						<span class="config-field-label">{{ $avt('config:label_image_extensions', 'Image file extensions for metadata scan') }}</span>
						<input
							v-model="imageExtensionsInput"
							type="text"
							class="config-text-input"
							:disabled="saving"
							:placeholder="$avt('config:placeholder_image_extensions', 'jpg,jpeg,tif,tiff,png,heic')"
						/>
					</label>

					<label class="config-field">
						<span class="config-field-label">{{ $avt('config:label_max_photos_persons', 'Max Photos persons per request') }}</span>
						<input
							v-model.number="configModel.photos.MAX_PHOTOS_PERSONS"
							type="number"
							min="1"
							step="1"
							class="config-text-input"
							:disabled="saving"
						/>
					</label>

					<label class="config-checkbox">
						<input v-model="configModel.photos.REINDEX_MISSING_ITEMS" type="checkbox" :disabled="saving" />
						<span>{{ $avt('config:label_reindex_missing_photos_items', 'Reindex images not found in Photos') }}</span>
					</label>

					<label class="config-field">
						<span class="config-field-label">{{ $avt('config:label_name_conflict_overlap_threshold', 'Name conflict face overlap threshold') }}</span>
						<input
							v-model.number="configModel.analysis.CHECKS.NAME_CONFLICT_OVERLAP_THRESHOLD"
							type="number"
							min="0"
							max="1"
							step="0.01"
							class="config-text-input"
							:disabled="saving"
						/>
						<span class="config-card-desc">
							{{ $avt('config:hint_name_conflict_overlap_threshold', 'Minimum overlap for treating two face boxes as the same face. Higher values reduce false positives in pair and group photos.') }}
						</span>
					</label>

					<label class="config-checkbox">
						<input
							v-model="configModel.analysis.CHECKS.NAME_CONFLICT_REQUIRE_MUTUAL_BEST_MATCH"
							type="checkbox"
							:disabled="saving"
						/>
						<span>{{ $avt('config:label_name_conflict_require_mutual_best_match', 'Require mutual best face match for name conflicts') }}</span>
					</label>

					<label class="config-field">
						<span class="config-field-label">{{ $avt('config:label_name_conflict_min_best_match_margin', 'Minimum best-match margin for name conflicts') }}</span>
						<input
							v-model.number="configModel.analysis.CHECKS.NAME_CONFLICT_MIN_BEST_MATCH_MARGIN"
							type="number"
							min="0"
							max="1"
							step="0.01"
							class="config-text-input"
							:disabled="saving || !configModel.analysis.CHECKS.NAME_CONFLICT_REQUIRE_MUTUAL_BEST_MATCH"
						/>
						<span class="config-card-desc">
							{{ $avt('config:hint_name_conflict_min_best_match_margin', 'The best matching face must be this much better than the second-best candidate. Increase this for close pair photos.') }}
						</span>
					</label>

					<div class="config-field">
						<span class="config-field-label">{{ $avt('config:label_sidecar_lookup_variants', 'Sidecar lookup variants') }}</span>
						<div class="config-form-grid">
							<label
								v-for="option in sidecarLookupOptions"
								:key="option.value"
								class="config-checkbox"
							>
								<input
									v-model="configModel.files.SIDECAR_LOOKUP_VARIANTS"
									type="checkbox"
									:value="option.value"
									:disabled="saving"
								/>
								<span>{{ option.label }}</span>
							</label>
						</div>
						<span class="config-card-desc">
							{{ $avt('config:hint_sidecar_lookup_variants', 'Select which XMP sidecar naming and subfolder variants should be checked. All are enabled by default.') }}
						</span>
					</div>
				</div>
			</section>

			<section class="config-card">
				<div class="sm-section-title">{{ $avt('config:section_analysis', 'Analysis') }}</div>
				<div class="config-card-desc">{{ $avt('config:section_analysis_desc', 'Select which checks should be performed during analysis runs.') }}</div>

				<div class="config-form-grid">
					<label class="config-checkbox">
						<input v-model="configModel.analysis.CHECKS.DUPLICATE_FACES" type="checkbox" :disabled="saving" />
						<span>{{ $avt('config:label_check_duplicate_faces', 'Check for duplicate face markings') }}</span>
					</label>

					<label class="config-checkbox">
						<input v-model="configModel.analysis.CHECKS.POSITION_DEVIATIONS" type="checkbox" :disabled="saving" />
						<span>{{ $avt('config:label_check_position_deviations', 'Check for deviating face positions') }}</span>
					</label>

					<label class="config-checkbox">
						<input v-model="configModel.analysis.CHECKS.POSITION_DEVIATIONS_INCLUDE_PHOTOS" type="checkbox" :disabled="saving" />
						<span>{{ $avt('config:label_check_position_deviations_include_photos', 'Include Photos face positions') }}</span>
					</label>

					<label class="config-checkbox">
						<input v-model="configModel.analysis.CHECKS.DIMENSION_ISSUES" type="checkbox" :disabled="saving" />
						<span>{{ $avt('config:label_check_dimension_issues', 'Check for dimension issues') }}</span>
					</label>

					<label class="config-checkbox">
						<input v-model="configModel.analysis.CHECKS.NAME_CONFLICTS" type="checkbox" :disabled="saving" />
						<span>{{ $avt('config:label_check_name_conflicts', 'Check for name conflicts') }}</span>
					</label>

					<label class="config-checkbox">
						<input v-model="configModel.analysis.CHECKS.NAME_CONFLICTS_INCLUDE_PHOTOS" type="checkbox" :disabled="saving" />
						<span>{{ $avt('config:label_check_name_conflicts_include_photos', 'Include Photos person names') }}</span>
					</label>

				</div>
			</section>

			<section class="config-card">
				<div class="sm-section-title">{{ $avt('config:section_face_match', 'Face matching') }}</div>
				<div class="config-card-desc">{{ $avt('config:section_face_match_desc', 'Configure where file-face searches should look for matching names.') }}</div>

				<div class="config-form-grid">
					<label class="config-field">
						<span class="config-field-label">{{ $avt('config:label_face_match_file_source_scope', 'Source scope for file-face search') }}</span>
						<select v-model="configModel.face_match.FILE_MATCH_SOURCE_SCOPE" class="config-select" :disabled="saving">
							<option value="both">{{ $avt('config:option_face_match_scope_both', 'in both') }}</option>
							<option value="photos">{{ $avt('config:option_face_match_scope_photos', 'only in Photos') }}</option>
							<option value="metadata">{{ $avt('config:option_face_match_scope_metadata', 'only in metadata') }}</option>
						</select>
					</label>

					<label class="config-field">
						<span class="config-field-label">{{ $avt('config:label_face_match_person_sort_order', 'Person sort order for face matching') }}</span>
						<select v-model="configModel.face_match.PERSON_SORT_ORDER" class="config-select" :disabled="saving">
							<option value="id_desc">{{ $avt('config:option_face_match_person_sort_id_desc', 'ID descending') }}</option>
							<option value="id_asc">{{ $avt('config:option_face_match_person_sort_id_asc', 'ID ascending') }}</option>
							<option value="none">{{ $avt('config:option_face_match_person_sort_none', 'No sorting') }}</option>
						</select>
					</label>

				</div>
			</section>

			<section class="config-card">
				<div class="sm-section-title">{{ $avt('config:section_review', 'Review') }}</div>
				<div class="config-card-desc">{{ $avt('config:section_review_desc', 'Select optional support behavior for the checks view.') }}</div>

				<div class="config-form-grid">
					<label class="config-checkbox">
						<input v-model="configModel.review.OPTIONS.DUPLICATE_FACE_SUGGESTIONS" type="checkbox" :disabled="saving" />
						<span>{{ $avt('config:label_review_duplicate_face_suggestions', 'Suggest likely valid duplicate face markings') }}</span>
					</label>

					<div class="config-field">
						<span class="config-field-label">{{ $avt('config:label_review_ignore_lists', 'Ignore lists for checks') }}</span>
						<div
							v-for="ignoreList in checksIgnoreListConfigs"
							:key="ignoreList.reviewType"
							class="config-field"
						>
							<label class="config-checkbox">
									<input
										v-model="configModel.review.CHECKS_IGNORE_LISTS[ignoreList.enabledKey]"
										type="checkbox"
										:disabled="saving"
									/>
									<span>{{ ignoreList.label }}</span>
								</label>
							</div>
						</div>

					<label
						class="config-field"
						:title="$avt('config:tooltip_check_single_source_of_truth', 'Automatically the value from this source is suggested for corrections.')"
					>
						<span class="config-field-label">{{ $avt('config:label_check_single_source_of_truth', 'Single Source of Truth for checks') }}</span>
						<select v-model="configModel.analysis.CHECKS.SINGLE_SOURCE_OF_TRUTH" class="config-select" :disabled="saving">
							<option value="">{{ $avt('config:option_check_single_source_of_truth_none', 'None') }}</option>
							<option
								v-for="option in checksSingleSourceOptions"
								:key="option.value"
								:value="option.value"
							>{{ option.label }}</option>
						</select>
					</label>
				</div>
			</section>

			<section class="config-card">
				<div class="sm-section-title">{{ $avt('config:section_debugging', 'Debugging') }}</div>
				<div class="config-card-desc">{{ $avt('config:section_debugging_desc', 'Diagnostic options for backend request and status troubleshooting.') }}</div>

				<div class="config-form-grid">
					<label class="config-checkbox" :title="$avt('config:hint_backend_debug_enabled', 'Writes backend request and status diagnostics to a rotating package log. Keep disabled during normal operation.')">
						<input
							v-model="configModel.debug.BACKEND_DEBUG_ENABLED"
							type="checkbox"
							:disabled="saving"
						/>
						<span>{{ $avt('config:label_backend_debug_enabled', 'Enable backend debug log') }}</span>
					</label>
					<div class="config-card-desc">
						{{ $avt('config:hint_backend_debug_log_path', 'Log path: {path}', { path: backendDebugLogPath || configModel.debug.BACKEND_DEBUG_LOG_PATH || 'backend-debug.log' }) }}
					</div>
				</div>
			</section>
		</div>
	</section>
</template>

<script>
export default {
	name: 'ConfigurationView',
	data() {
		return {
			loading: false,
			saving: false,
			message: '',
			configPath: '',
			backendDebugLogPath: '',
			configModel: this.createDefaultConfig(),
			imageExtensionsInput: '',
			checksIgnoreListsStatus: this.createDefaultChecksIgnoreListsStatus(),
		};
	},
	computed: {
		sidecarLookupOptions() {
			return [
				{ value: 'same_dir_stem', label: this.$avt('config:label_sidecar_variant_same_dir_stem', 'Same folder: image.xmp') },
				{ value: 'same_dir_filename', label: this.$avt('config:label_sidecar_variant_same_dir_filename', 'Same folder: image.jpg.xmp') },
				{ value: 'xmp_dir_stem', label: this.$avt('config:label_sidecar_variant_xmp_dir_stem', 'xmp subfolder: xmp/image.xmp') },
				{ value: 'xmp_dir_filename', label: this.$avt('config:label_sidecar_variant_xmp_dir_filename', 'xmp subfolder: xmp/image.jpg.xmp') },
			];
		},
		checksSingleSourceOptions() {
			const options = [
				{ value: 'photos', label: this.$avt('config:option_check_single_source_of_truth_photos', 'Photos') },
			];
			const formatOptions = [
				{ value: 'acd', label: 'ACD' },
				{ value: 'microsoft', label: 'Microsoft' },
				{ value: 'mwg_regions', label: 'MWG_REGIONS' },
			];
			const storageOptions = [
				{ value: 'any', label: this.$avt('config:option_check_single_source_location_any', 'egal') },
				{ value: 'embedded', label: this.$avt('config:option_check_single_source_location_embedded', 'eingebettet') },
				{ value: 'sidecar', label: this.$avt('config:option_check_single_source_location_sidecar', 'Sidecar') },
			];
			for (const format of formatOptions) {
				for (const storage of storageOptions) {
					options.push({
						value: `metadata:${format.value}:${storage.value}`,
						label: `${format.label} | ${storage.label}`,
					});
				}
			}
			return options;
		},
		checksIgnoreListConfigs() {
			return [
				{
					reviewType: 'duplicate_faces',
					enabledKey: 'DUPLICATE_FACES_ENABLED',
					label: this.$avt('config:label_check_ignore_list_duplicate_faces', 'Ignore list for duplicate face markings'),
				},
				{
					reviewType: 'position_deviations',
					enabledKey: 'POSITION_DEVIATIONS_ENABLED',
					label: this.$avt('config:label_check_ignore_list_position_deviations', 'Ignore list for deviating face positions'),
				},
				{
					reviewType: 'name_conflicts',
					enabledKey: 'NAME_CONFLICTS_ENABLED',
					label: this.$avt('config:label_check_ignore_list_name_conflicts', 'Ignore list for name conflicts'),
				},
			];
		},
	},
	mounted() {
		this.loadConfig();
	},
	methods: {
		escapeRegExp(value) {
			return String(value || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
		},
		createDefaultConfig() {
			return {
				files: {
					USE_EXIFTOOL: false,
					CHECK_EXIFTOOL_UPDATES: true,
					USE_EXIFTOOL_FOR_SIDECARS: false,
					PREFER_EXIFTOOL_FOR_CONTEXT: false,
					PATHEXIFTOOL: 'exiftool',
					USE_MANUAL_PATHEXIFTOOL: false,
					MANUAL_PATHEXIFTOOL: '',
					IMAGE_EXTENSIONS_NATIVE_ONLY: true,
					IMAGE_EXTENSIONS: ['jpg', 'jpeg', 'tif', 'tiff', 'png', 'heic', 'heif', 'dng', 'cr2', 'cr3', 'nef', 'nrw', 'arw', 'orf', 'rw2', 'raf', 'pef'],
					EXIFTOOL_IMAGE_EXTENSIONS: [],
					SIDECAR_LOOKUP_VARIANTS: ['same_dir_stem', 'same_dir_filename', 'xmp_dir_stem', 'xmp_dir_filename'],
				},
				metadata: {
					SCHEMAS: {
						ACD: true,
						MICROSOFT: true,
						MWG_REGIONS: true,
					},
				},
				analysis: {
					CHECKS: {
						DUPLICATE_FACES: true,
						POSITION_DEVIATIONS: true,
						POSITION_DEVIATIONS_INCLUDE_PHOTOS: true,
						DIMENSION_ISSUES: true,
						NAME_CONFLICTS: true,
						NAME_CONFLICTS_INCLUDE_PHOTOS: true,
						NAME_CONFLICT_OVERLAP_THRESHOLD: 0.75,
						NAME_CONFLICT_REQUIRE_MUTUAL_BEST_MATCH: true,
						NAME_CONFLICT_MIN_BEST_MATCH_MARGIN: 0.05,
						SINGLE_SOURCE_OF_TRUTH: '',
					},
				},
				review: {
					OPTIONS: {
						DUPLICATE_FACE_SUGGESTIONS: true,
					},
					CHECKS_IGNORE_LISTS: {
						DUPLICATE_FACES_ENABLED: true,
						POSITION_DEVIATIONS_ENABLED: true,
						NAME_CONFLICTS_ENABLED: true,
					},
				},
				photos: {
					MAX_PHOTOS_PERSONS: 5000,
					REINDEX_MISSING_ITEMS: false,
				},
				face_match: {
					FILE_MATCH_SOURCE_SCOPE: 'both',
					PERSON_SORT_ORDER: 'id_desc',
				},
				debug: {
					IO_METRICS_ENABLED: false,
					BACKEND_DEBUG_ENABLED: false,
					BACKEND_DEBUG_LOG_PATH: '',
					BACKEND_DEBUG_LOG_MAX_BYTES: 1048576,
					BACKEND_DEBUG_LOG_BACKUPS: 3,
				},
			};
		},
		createDefaultChecksIgnoreListsStatus() {
			return {
				duplicate_faces: { count: 0, path: '', enabled: true },
				position_deviations: { count: 0, path: '', enabled: true },
				name_conflicts: { count: 0, path: '', enabled: true },
			};
		},
		getSynoToken() {
			return (SYNO && SYNO.SDS && SYNO.SDS.Session && SYNO.SDS.Session.SynoToken) || '';
		},
		readCookie(name) {
			const match = document.cookie.match(new RegExp('(?:^|; )' + this.escapeRegExp(name) + '=([^;]*)'));
			return match ? decodeURIComponent(match[1]) : '';
		},
		normalizeImageExtensions(value, fallback = []) {
			const source = Array.isArray(value) ? value : String(value || '').split(/[\s,;]+/);
			const normalized = source
				.map((entry) => String(entry || '').trim().toLowerCase().replace(/^\./, ''))
				.filter((entry, index, arr) => entry && arr.indexOf(entry) === index);
			return normalized.length ? normalized : [...fallback];
		},
		normalizeSelectionList(value, allowedValues, fallback = []) {
			const source = Array.isArray(value) ? value : [];
			const allowed = Array.isArray(allowedValues) ? allowedValues : [];
			const normalized = source
				.map((entry) => String(entry || '').trim())
				.filter((entry, index, arr) => entry && allowed.includes(entry) && arr.indexOf(entry) === index);
			return normalized.length ? normalized : [...fallback];
		},
		normalizeChecksIgnoreListsStatus(value) {
			const source = (value && typeof value === 'object' && !Array.isArray(value))
				? value
				: {};
			const defaults = this.createDefaultChecksIgnoreListsStatus();
			const normalized = {};
			for (const reviewType of Object.keys(defaults)) {
				const entry = (source[reviewType] && typeof source[reviewType] === 'object' && !Array.isArray(source[reviewType]))
					? source[reviewType]
					: {};
				normalized[reviewType] = {
					count: Math.max(0, Number(entry.count) || 0),
					path: String(entry.path || ''),
					enabled: Boolean(entry.enabled ?? defaults[reviewType].enabled),
				};
			}
			return normalized;
		},
		getChecksIgnoreListStatus(reviewType) {
			return this.checksIgnoreListsStatus[reviewType] || { count: 0, path: '', enabled: true };
		},
		clampNumber(value, min, max, fallback) {
			const numeric = Number(value);
			if (!Number.isFinite(numeric)) {
				return fallback;
			}
			if (numeric < min) {
				return min;
			}
			if (numeric > max) {
				return max;
			}
			return numeric;
		},
		normalizeChecksSingleSourceOfTruth(value, fallback = '') {
			const normalized = String(value || '').trim().toLowerCase();
			const allowed = this.checksSingleSourceOptions.map((option) => option.value);
			return allowed.includes(normalized) ? normalized : fallback;
		},
		formatImageExtensions(value) {
			return this.normalizeImageExtensions(value).join(', ');
		},
		collectDsmCookies() {
			return {
				_SSID: this.readCookie('_SSID'),
				id: this.readCookie('id'),
				did: this.readCookie('did'),
			};
		},
		async callApi(apiPath, body = {}) {
			const resp = await fetch(apiPath, {
				method: 'POST',
				credentials: 'include',
				headers: {
					'Content-Type': 'application/json',
					'X-SYNO-TOKEN': this.getSynoToken(),
				},
				body: JSON.stringify({
					...body,
					cookies: this.collectDsmCookies(),
					synoToken: this.getSynoToken(),
				}),
			});
			const data = await resp.json().catch(() => ({}));
			if (!resp.ok || data.success === false) {
				const backendError = data.error || `HTTP ${resp.status}`;
				throw new Error(typeof backendError === 'string' ? backendError : JSON.stringify(backendError));
			}
			return data;
		},
		normalizeConfig(input) {
			const root = (input && typeof input === 'object' && !Array.isArray(input)) ? input : {};
			const defaults = this.createDefaultConfig();
			const files = (root.files && typeof root.files === 'object' && !Array.isArray(root.files)) ? root.files : {};
			const metadata = (root.metadata && typeof root.metadata === 'object' && !Array.isArray(root.metadata)) ? root.metadata : {};
			const schemas = (metadata.SCHEMAS && typeof metadata.SCHEMAS === 'object' && !Array.isArray(metadata.SCHEMAS)) ? metadata.SCHEMAS : {};
			const analysis = (root.analysis && typeof root.analysis === 'object' && !Array.isArray(root.analysis)) ? root.analysis : {};
			const checks = (analysis.CHECKS && typeof analysis.CHECKS === 'object' && !Array.isArray(analysis.CHECKS)) ? analysis.CHECKS : {};
			const review = (root.review && typeof root.review === 'object' && !Array.isArray(root.review)) ? root.review : {};
			const reviewOptions = (review.OPTIONS && typeof review.OPTIONS === 'object' && !Array.isArray(review.OPTIONS)) ? review.OPTIONS : {};
			const reviewIgnoreLists = (review.CHECKS_IGNORE_LISTS && typeof review.CHECKS_IGNORE_LISTS === 'object' && !Array.isArray(review.CHECKS_IGNORE_LISTS)) ? review.CHECKS_IGNORE_LISTS : {};
			const photos = (root.photos && typeof root.photos === 'object' && !Array.isArray(root.photos)) ? root.photos : {};
			const faceMatch = (root.face_match && typeof root.face_match === 'object' && !Array.isArray(root.face_match)) ? root.face_match : {};
			const debug = (root.debug && typeof root.debug === 'object' && !Array.isArray(root.debug)) ? root.debug : {};

			const imageExtensions = this.normalizeImageExtensions(files.IMAGE_EXTENSIONS, defaults.files.IMAGE_EXTENSIONS);
			const exiftoolImageExtensions = this.normalizeImageExtensions(files.EXIFTOOL_IMAGE_EXTENSIONS, []);
			const sidecarLookupVariants = this.normalizeSelectionList(
				files.SIDECAR_LOOKUP_VARIANTS,
				this.sidecarLookupOptions.map((option) => option.value),
				defaults.files.SIDECAR_LOOKUP_VARIANTS
			);

			return {
				...root,
				files: {
					...files,
					USE_EXIFTOOL: Boolean(files.USE_EXIFTOOL ?? defaults.files.USE_EXIFTOOL),
					CHECK_EXIFTOOL_UPDATES: Boolean(files.CHECK_EXIFTOOL_UPDATES ?? defaults.files.CHECK_EXIFTOOL_UPDATES),
					USE_EXIFTOOL_FOR_SIDECARS: Boolean(files.USE_EXIFTOOL_FOR_SIDECARS ?? defaults.files.USE_EXIFTOOL_FOR_SIDECARS),
					PREFER_EXIFTOOL_FOR_CONTEXT: Boolean(files.PREFER_EXIFTOOL_FOR_CONTEXT ?? defaults.files.PREFER_EXIFTOOL_FOR_CONTEXT),
					PATHEXIFTOOL: String(files.PATHEXIFTOOL || defaults.files.PATHEXIFTOOL),
					USE_MANUAL_PATHEXIFTOOL: Boolean(files.USE_MANUAL_PATHEXIFTOOL ?? defaults.files.USE_MANUAL_PATHEXIFTOOL),
					MANUAL_PATHEXIFTOOL: String(files.MANUAL_PATHEXIFTOOL || defaults.files.MANUAL_PATHEXIFTOOL),
					IMAGE_EXTENSIONS_NATIVE_ONLY: Boolean(files.IMAGE_EXTENSIONS_NATIVE_ONLY ?? defaults.files.IMAGE_EXTENSIONS_NATIVE_ONLY),
					IMAGE_EXTENSIONS: imageExtensions,
					EXIFTOOL_IMAGE_EXTENSIONS: exiftoolImageExtensions,
					SIDECAR_LOOKUP_VARIANTS: sidecarLookupVariants,
				},
				metadata: {
					...metadata,
					SCHEMAS: {
						...schemas,
						ACD: Boolean(schemas.ACD ?? defaults.metadata.SCHEMAS.ACD),
						MICROSOFT: Boolean(schemas.MICROSOFT ?? defaults.metadata.SCHEMAS.MICROSOFT),
						MWG_REGIONS: Boolean(schemas.MWG_REGIONS ?? defaults.metadata.SCHEMAS.MWG_REGIONS),
					},
				},
				analysis: {
					...analysis,
					CHECKS: {
						...checks,
						DUPLICATE_FACES: Boolean(checks.DUPLICATE_FACES ?? defaults.analysis.CHECKS.DUPLICATE_FACES),
						POSITION_DEVIATIONS: Boolean(checks.POSITION_DEVIATIONS ?? defaults.analysis.CHECKS.POSITION_DEVIATIONS),
						POSITION_DEVIATIONS_INCLUDE_PHOTOS: Boolean(checks.POSITION_DEVIATIONS_INCLUDE_PHOTOS ?? defaults.analysis.CHECKS.POSITION_DEVIATIONS_INCLUDE_PHOTOS),
						DIMENSION_ISSUES: Boolean(checks.DIMENSION_ISSUES ?? defaults.analysis.CHECKS.DIMENSION_ISSUES),
						NAME_CONFLICTS: Boolean(checks.NAME_CONFLICTS ?? defaults.analysis.CHECKS.NAME_CONFLICTS),
						NAME_CONFLICTS_INCLUDE_PHOTOS: Boolean(checks.NAME_CONFLICTS_INCLUDE_PHOTOS ?? defaults.analysis.CHECKS.NAME_CONFLICTS_INCLUDE_PHOTOS),
						NAME_CONFLICT_OVERLAP_THRESHOLD: this.clampNumber(
							checks.NAME_CONFLICT_OVERLAP_THRESHOLD,
							0,
							1,
							defaults.analysis.CHECKS.NAME_CONFLICT_OVERLAP_THRESHOLD
						),
						NAME_CONFLICT_REQUIRE_MUTUAL_BEST_MATCH: Boolean(checks.NAME_CONFLICT_REQUIRE_MUTUAL_BEST_MATCH ?? defaults.analysis.CHECKS.NAME_CONFLICT_REQUIRE_MUTUAL_BEST_MATCH),
						NAME_CONFLICT_MIN_BEST_MATCH_MARGIN: this.clampNumber(
							checks.NAME_CONFLICT_MIN_BEST_MATCH_MARGIN,
							0,
							1,
							defaults.analysis.CHECKS.NAME_CONFLICT_MIN_BEST_MATCH_MARGIN
						),
						SINGLE_SOURCE_OF_TRUTH: this.normalizeChecksSingleSourceOfTruth(
							checks.SINGLE_SOURCE_OF_TRUTH,
							defaults.analysis.CHECKS.SINGLE_SOURCE_OF_TRUTH
						),
					},
				},
				review: {
					...review,
					OPTIONS: {
						...reviewOptions,
						DUPLICATE_FACE_SUGGESTIONS: Boolean(
							reviewOptions.DUPLICATE_FACE_SUGGESTIONS
							?? checks.DUPLICATE_FACE_SUGGESTIONS
							?? defaults.review.OPTIONS.DUPLICATE_FACE_SUGGESTIONS
						),
					},
					CHECKS_IGNORE_LISTS: {
						...reviewIgnoreLists,
						DUPLICATE_FACES_ENABLED: Boolean(
							reviewIgnoreLists.DUPLICATE_FACES_ENABLED
							?? defaults.review.CHECKS_IGNORE_LISTS.DUPLICATE_FACES_ENABLED
						),
						POSITION_DEVIATIONS_ENABLED: Boolean(
							reviewIgnoreLists.POSITION_DEVIATIONS_ENABLED
							?? defaults.review.CHECKS_IGNORE_LISTS.POSITION_DEVIATIONS_ENABLED
						),
						NAME_CONFLICTS_ENABLED: Boolean(
							reviewIgnoreLists.NAME_CONFLICTS_ENABLED
							?? defaults.review.CHECKS_IGNORE_LISTS.NAME_CONFLICTS_ENABLED
						),
					},
				},
				photos: {
					...photos,
					MAX_PHOTOS_PERSONS: Math.max(1, Number(photos.MAX_PHOTOS_PERSONS) || defaults.photos.MAX_PHOTOS_PERSONS),
					REINDEX_MISSING_ITEMS: Boolean(photos.REINDEX_MISSING_ITEMS ?? defaults.photos.REINDEX_MISSING_ITEMS),
				},
				face_match: {
					...faceMatch,
					FILE_MATCH_SOURCE_SCOPE: ['both', 'photos', 'metadata'].includes(String(faceMatch.FILE_MATCH_SOURCE_SCOPE || '').trim().toLowerCase())
						? String(faceMatch.FILE_MATCH_SOURCE_SCOPE || '').trim().toLowerCase()
						: defaults.face_match.FILE_MATCH_SOURCE_SCOPE,
					PERSON_SORT_ORDER: ['id_desc', 'id_asc', 'none'].includes(String(faceMatch.PERSON_SORT_ORDER || '').trim().toLowerCase())
						? String(faceMatch.PERSON_SORT_ORDER || '').trim().toLowerCase()
						: defaults.face_match.PERSON_SORT_ORDER,
				},
				debug: {
					...debug,
					IO_METRICS_ENABLED: Boolean(debug.IO_METRICS_ENABLED ?? defaults.debug.IO_METRICS_ENABLED),
					BACKEND_DEBUG_ENABLED: Boolean(debug.BACKEND_DEBUG_ENABLED ?? defaults.debug.BACKEND_DEBUG_ENABLED),
					BACKEND_DEBUG_LOG_PATH: String(debug.BACKEND_DEBUG_LOG_PATH || defaults.debug.BACKEND_DEBUG_LOG_PATH),
					BACKEND_DEBUG_LOG_MAX_BYTES: Math.max(65536, Math.min(10485760, Number(debug.BACKEND_DEBUG_LOG_MAX_BYTES) || defaults.debug.BACKEND_DEBUG_LOG_MAX_BYTES)),
					BACKEND_DEBUG_LOG_BACKUPS: Math.max(1, Math.min(10, Number(debug.BACKEND_DEBUG_LOG_BACKUPS) || defaults.debug.BACKEND_DEBUG_LOG_BACKUPS)),
				},
			};
		},
		applyDefaults() {
			const exiftoolFiles = {
				USE_EXIFTOOL: this.configModel.files.USE_EXIFTOOL,
				CHECK_EXIFTOOL_UPDATES: this.configModel.files.CHECK_EXIFTOOL_UPDATES,
				USE_EXIFTOOL_FOR_SIDECARS: this.configModel.files.USE_EXIFTOOL_FOR_SIDECARS,
				PREFER_EXIFTOOL_FOR_CONTEXT: this.configModel.files.PREFER_EXIFTOOL_FOR_CONTEXT,
				PATHEXIFTOOL: this.configModel.files.PATHEXIFTOOL,
				USE_MANUAL_PATHEXIFTOOL: this.configModel.files.USE_MANUAL_PATHEXIFTOOL,
				MANUAL_PATHEXIFTOOL: this.configModel.files.MANUAL_PATHEXIFTOOL,
				IMAGE_EXTENSIONS_NATIVE_ONLY: this.configModel.files.IMAGE_EXTENSIONS_NATIVE_ONLY,
				EXIFTOOL_IMAGE_EXTENSIONS: this.configModel.files.EXIFTOOL_IMAGE_EXTENSIONS,
			};
			this.configModel = this.createDefaultConfig();
			this.configModel.files = {
				...this.configModel.files,
				...exiftoolFiles,
			};
			this.imageExtensionsInput = this.formatImageExtensions(this.configModel.files.IMAGE_EXTENSIONS);
			this.message = this.$avt('config:output_defaults_applied', 'Default values loaded into the editor.');
		},
		async loadConfig() {
			this.loading = true;
			this.message = '';
			try {
				const data = await this.callApi('/webman/3rdparty/AV_ImgData/index.cgi/api/config_get');
				this.configPath = (data && data.data && data.data.config_path) || '';
				this.backendDebugLogPath = (data && data.data && data.data.backend_debug_log_path) || '';
				this.configModel = this.normalizeConfig(data && data.data && data.data.config);
				this.imageExtensionsInput = this.formatImageExtensions(this.configModel.files.IMAGE_EXTENSIONS);
				this.checksIgnoreListsStatus = this.normalizeChecksIgnoreListsStatus(data && data.data && data.data.checks_ignore_lists);
				this.message = '';
			} catch (err) {
				this.message = `Error: ${err.message}`;
			} finally {
				this.loading = false;
			}
		},
		async saveConfig() {
			this.saving = true;
			this.message = '';
			try {
				const payloadConfig = {
					...this.configModel,
					files: {
						...this.configModel.files,
						IMAGE_EXTENSIONS: this.normalizeImageExtensions(
							this.imageExtensionsInput,
							this.createDefaultConfig().files.IMAGE_EXTENSIONS
						),
					},
				};
				const normalized = this.normalizeConfig(payloadConfig);
				const data = await this.callApi('/webman/3rdparty/AV_ImgData/index.cgi/api/config_save', { config: normalized });
				this.configPath = (data && data.data && data.data.config_path) || this.configPath;
				this.backendDebugLogPath = (data && data.data && data.data.backend_debug_log_path) || this.backendDebugLogPath;
				this.configModel = this.normalizeConfig(data && data.data && data.data.config);
				this.imageExtensionsInput = this.formatImageExtensions(this.configModel.files.IMAGE_EXTENSIONS);
				this.checksIgnoreListsStatus = this.normalizeChecksIgnoreListsStatus(data && data.data && data.data.checks_ignore_lists);
				this.message = this.$avt('config:message_saved', 'Configuration saved.');
			} catch (err) {
				this.message = `Error: ${err.message}`;
			} finally {
				this.saving = false;
			}
		},
	},
};
</script>
