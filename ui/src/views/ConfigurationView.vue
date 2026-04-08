<template>
	<section class="panel">
		<div class="panel-head">
			<div class="sm-section-title">{{ $t('config:title', 'Configuration') }}</div>
		</div>

		<div class="config-actions config-actions-right">
			<v-button @click="loadConfig" :disabled="loading || saving" style="width: 160px;">
				{{ $t('config:button_reload', 'Reload') }}
			</v-button>
			<v-button @click="applyDefaults" :disabled="loading || saving" style="width: 160px;">
				{{ $t('config:button_defaults', 'Defaults') }}
			</v-button>
			<v-button @click="saveConfig" :disabled="loading || saving" style="width: 160px;">
				{{ $t('config:button_save', 'Save') }}
			</v-button>
		</div>

		<div v-if="message" class="config-message">{{ message }}</div>

		<div v-if="loading" class="config-loading">
			<span class="sm-loader"></span>
			{{ $t('config:loading', 'Loading configuration...') }}
		</div>

		<div v-else class="config-layout">
			<section class="config-card">
				<div class="sm-section-title">{{ $t('config:section_runtime', 'Runtime settings') }}</div>
				<div class="config-card-desc">{{ $t('config:config_path', 'Config path: {path}', { path: configPath || '-' }) }}</div>

				<div class="config-form-grid">
					<label class="config-checkbox">
						<input v-model="configModel.metadata.SCHEMAS.ACD" type="checkbox" :disabled="saving" />
						<span>{{ $t('config:label_schema_acd', 'Read ACDSee metadata') }}</span>
					</label>

					<label class="config-checkbox">
						<input v-model="configModel.metadata.SCHEMAS.MICROSOFT" type="checkbox" :disabled="saving" />
						<span>{{ $t('config:label_schema_microsoft', 'Read Microsoft face metadata') }}</span>
					</label>

					<label class="config-checkbox">
						<input v-model="configModel.metadata.SCHEMAS.MWG_REGIONS" type="checkbox" :disabled="saving" />
						<span>{{ $t('config:label_schema_mwg_regions', 'Read MWG face regions metadata') }}</span>
					</label>

					<label class="config-field">
						<span class="config-field-label">{{ $t('config:label_image_extensions', 'Image file extensions for metadata scan') }}</span>
						<input
							v-model="imageExtensionsInput"
							type="text"
							class="config-text-input"
							:disabled="saving"
							:placeholder="$t('config:placeholder_image_extensions', 'jpg,jpeg,tif,tiff,png,heic')"
						/>
					</label>

					<label class="config-field">
						<span class="config-field-label">{{ $t('config:label_max_photos_persons', 'Max Photos persons per request') }}</span>
						<input
							v-model.number="configModel.photos.MAX_PHOTOS_PERSONS"
							type="number"
							min="1"
							step="1"
							class="config-text-input"
							:disabled="saving"
						/>
					</label>

					<div class="config-field">
						<span class="config-field-label">{{ $t('config:label_sidecar_lookup_variants', 'Sidecar lookup variants') }}</span>
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
							{{ $t('config:hint_sidecar_lookup_variants', 'Select which XMP sidecar naming and subfolder variants should be checked. All are enabled by default.') }}
						</span>
					</div>
				</div>
			</section>

			<section class="config-card">
				<div class="sm-section-title">{{ $t('config:section_analysis', 'Analysis') }}</div>
				<div class="config-card-desc">{{ $t('config:section_analysis_desc', 'Select which checks should be performed during analysis runs.') }}</div>

				<div class="config-form-grid">
					<label class="config-checkbox">
						<input v-model="configModel.analysis.CHECKS.DUPLICATE_FACES" type="checkbox" :disabled="saving" />
						<span>{{ $t('config:label_check_duplicate_faces', 'Check for duplicate face markings') }}</span>
					</label>

					<label class="config-checkbox">
						<input v-model="configModel.analysis.CHECKS.POSITION_DEVIATIONS" type="checkbox" :disabled="saving" />
						<span>{{ $t('config:label_check_position_deviations', 'Check for deviating face positions') }}</span>
					</label>

					<label class="config-checkbox">
						<input v-model="configModel.analysis.CHECKS.DIMENSION_ISSUES" type="checkbox" :disabled="saving" />
						<span>{{ $t('config:label_check_dimension_issues', 'Check for dimension issues') }}</span>
					</label>

					<label class="config-checkbox">
						<input v-model="configModel.analysis.CHECKS.NAME_CONFLICTS" type="checkbox" :disabled="saving" />
						<span>{{ $t('config:label_check_name_conflicts', 'Check for name conflicts') }}</span>
					</label>
				</div>
			</section>

			<section class="config-card">
				<div class="sm-section-title">{{ $t('config:section_review', 'Review') }}</div>
				<div class="config-card-desc">{{ $t('config:section_review_desc', 'Select optional support behavior for the checks view.') }}</div>

				<div class="config-form-grid">
					<label class="config-checkbox">
						<input v-model="configModel.review.OPTIONS.DUPLICATE_FACE_SUGGESTIONS" type="checkbox" :disabled="saving" />
						<span>{{ $t('config:label_review_duplicate_face_suggestions', 'Suggest likely valid duplicate face markings') }}</span>
					</label>
				</div>
			</section>

			<section class="config-card">
				<div class="sm-section-title">{{ $t('config:section_face_match', 'Face matching') }}</div>
				<div class="config-card-desc">{{ $t('config:section_face_match_desc', 'Configure where file-face searches should look for matching names.') }}</div>

				<div class="config-form-grid">
					<label class="config-field">
						<span class="config-field-label">{{ $t('config:label_face_match_file_source_scope', 'Source scope for file-face search') }}</span>
						<select v-model="configModel.face_match.FILE_MATCH_SOURCE_SCOPE" class="config-select" :disabled="saving">
							<option value="both">{{ $t('config:option_face_match_scope_both', 'in both') }}</option>
							<option value="photos">{{ $t('config:option_face_match_scope_photos', 'only in Photos') }}</option>
							<option value="metadata">{{ $t('config:option_face_match_scope_metadata', 'only in metadata') }}</option>
						</select>
					</label>
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
			configModel: this.createDefaultConfig(),
			imageExtensionsInput: '',
		};
	},
	computed: {
		sidecarLookupOptions() {
			return [
				{ value: 'same_dir_stem', label: this.$t('config:label_sidecar_variant_same_dir_stem', 'Same folder: image.xmp') },
				{ value: 'same_dir_filename', label: this.$t('config:label_sidecar_variant_same_dir_filename', 'Same folder: image.jpg.xmp') },
				{ value: 'xmp_dir_stem', label: this.$t('config:label_sidecar_variant_xmp_dir_stem', 'xmp subfolder: xmp/image.xmp') },
				{ value: 'xmp_dir_filename', label: this.$t('config:label_sidecar_variant_xmp_dir_filename', 'xmp subfolder: xmp/image.jpg.xmp') },
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
					IMAGE_EXTENSIONS_NATIVE_ONLY: false,
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
						DIMENSION_ISSUES: true,
						NAME_CONFLICTS: true,
					},
				},
				review: {
					OPTIONS: {
						DUPLICATE_FACE_SUGGESTIONS: true,
					},
				},
				photos: {
					MAX_PHOTOS_PERSONS: 5000,
				},
				face_match: {
					FILE_MATCH_SOURCE_SCOPE: 'both',
				},
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
			const photos = (root.photos && typeof root.photos === 'object' && !Array.isArray(root.photos)) ? root.photos : {};
			const faceMatch = (root.face_match && typeof root.face_match === 'object' && !Array.isArray(root.face_match)) ? root.face_match : {};

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
						DIMENSION_ISSUES: Boolean(checks.DIMENSION_ISSUES ?? defaults.analysis.CHECKS.DIMENSION_ISSUES),
						NAME_CONFLICTS: Boolean(checks.NAME_CONFLICTS ?? defaults.analysis.CHECKS.NAME_CONFLICTS),
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
				},
				photos: {
					...photos,
					MAX_PHOTOS_PERSONS: Math.max(1, Number(photos.MAX_PHOTOS_PERSONS) || defaults.photos.MAX_PHOTOS_PERSONS),
				},
				face_match: {
					...faceMatch,
					FILE_MATCH_SOURCE_SCOPE: ['both', 'photos', 'metadata'].includes(String(faceMatch.FILE_MATCH_SOURCE_SCOPE || '').trim().toLowerCase())
						? String(faceMatch.FILE_MATCH_SOURCE_SCOPE || '').trim().toLowerCase()
						: defaults.face_match.FILE_MATCH_SOURCE_SCOPE,
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
				IMAGE_EXTENSIONS_NATIVE_ONLY: this.configModel.files.IMAGE_EXTENSIONS_NATIVE_ONLY,
				EXIFTOOL_IMAGE_EXTENSIONS: this.configModel.files.EXIFTOOL_IMAGE_EXTENSIONS,
			};
			this.configModel = this.createDefaultConfig();
			this.configModel.files = {
				...this.configModel.files,
				...exiftoolFiles,
			};
			this.imageExtensionsInput = this.formatImageExtensions(this.configModel.files.IMAGE_EXTENSIONS);
			this.message = this.$t('config:output_defaults_applied', 'Default values loaded into the editor.');
		},
		async loadConfig() {
			this.loading = true;
			this.message = '';
			try {
				const data = await this.callApi('/webman/3rdparty/AV_ImgData/index.cgi/api/config_get');
				this.configPath = (data && data.data && data.data.config_path) || '';
				this.configModel = this.normalizeConfig(data && data.data && data.data.config);
				this.imageExtensionsInput = this.formatImageExtensions(this.configModel.files.IMAGE_EXTENSIONS);
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
				this.configModel = this.normalizeConfig(data && data.data && data.data.config);
				this.imageExtensionsInput = this.formatImageExtensions(this.configModel.files.IMAGE_EXTENSIONS);
				this.message = this.$t('config:message_saved', 'Configuration saved.');
			} catch (err) {
				this.message = `Error: ${err.message}`;
			} finally {
				this.saving = false;
			}
		},
	},
};
</script>
