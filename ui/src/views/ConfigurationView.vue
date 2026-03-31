<template>
	<section class="panel">
		<div class="panel-head">
			<h1>{{ $t('config:title', 'Configuration') }}</h1>
		</div>

		<div class="config-actions">
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
				<div class="config-card-title">{{ $t('config:section_runtime', 'Runtime settings') }}</div>
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
				</div>
			</section>

			<section class="config-card">
				<div class="config-card-title">{{ $t('config:section_exiftool', 'ExifTool') }}</div>
				<div class="config-card-desc">{{ $t('config:section_exiftool_desc', 'Settings for optional ExifTool usage when reading embedded XMP metadata.') }}</div>

				<div class="config-form-grid">
					<label class="config-checkbox">
						<input v-model="configModel.files.USE_EXIFTOOL" type="checkbox" :disabled="saving" />
						<span>{{ $t('config:label_use_exiftool', 'Use ExifTool for embedded XMP') }}</span>
					</label>

					<template v-if="configModel.files.USE_EXIFTOOL">
						<label
							class="config-checkbox"
							:title="$t('config:hint_use_exiftool_for_sidecars', 'The native sidecar path usually works well and is faster. Only enable this when sidecar reading causes problems.')"
						>
							<input
								v-model="configModel.files.USE_EXIFTOOL_FOR_SIDECARS"
								type="checkbox"
								:disabled="saving"
							/>
							<span>{{ $t('config:label_use_exiftool_for_sidecars', 'Use ExifTool for XMP sidecars') }}</span>
						</label>

						<label
							class="config-checkbox"
							:title="$t('config:hint_prefer_exiftool_for_context', 'Native context readers are usually faster. Enable this only if ExifTool should be preferred for dimensions and orientation, otherwise ExifTool is only used as a fallback.')"
						>
							<input
								v-model="configModel.files.PREFER_EXIFTOOL_FOR_CONTEXT"
								type="checkbox"
								:disabled="saving"
							/>
							<span>{{ $t('config:label_prefer_exiftool_for_context', 'Prefer ExifTool for metadata context') }}</span>
						</label>
					</template>
				</div>

				<div v-if="exiftoolStatus.online && exiftoolStatus.online.unix_download_url" class="config-card-desc">
					{{ $t('config:exiftool_download_source', 'Latest ExifTool package will be downloaded from: {url}', { url: exiftoolStatus.online.unix_download_url }) }}
				</div>

				<div class="config-actions config-actions-right">
					<v-button @click="installExiftool" :disabled="loading || saving || exiftoolInstalling" style="width: 220px;">
						{{ exiftoolInstalling ? $t('config:button_exiftool_installing', 'Installing ExifTool...') : $t('config:button_exiftool_install', 'Download and install ExifTool') }}
					</v-button>
					<v-button
						v-if="hasBundledExiftool"
						@click="removeExiftool"
						:disabled="loading || saving || exiftoolInstalling || exiftoolRemoving"
						style="width: 220px;"
					>
						{{ exiftoolRemoving ? $t('config:button_exiftool_removing', 'Removing ExifTool...') : $t('config:button_exiftool_remove', 'Remove ExifTool') }}
					</v-button>
				</div>
			</section>

			<section class="config-card">
				<div class="config-card-title">{{ $t('config:section_analysis', 'Analysis') }}</div>
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
				<div class="config-card-title">{{ $t('config:section_review', 'Review') }}</div>
				<div class="config-card-desc">{{ $t('config:section_review_desc', 'Select optional support behavior for the checks view.') }}</div>

				<div class="config-form-grid">
					<label class="config-checkbox">
						<input v-model="configModel.review.OPTIONS.DUPLICATE_FACE_SUGGESTIONS" type="checkbox" :disabled="saving" />
						<span>{{ $t('config:label_review_duplicate_face_suggestions', 'Suggest likely valid duplicate face markings') }}</span>
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
			exiftoolStatus: {},
			exiftoolInstalling: false,
			exiftoolRemoving: false,
		};
	},
	computed: {
		hasBundledExiftool() {
			const resolvedPath = this.exiftoolStatus && this.exiftoolStatus.local && this.exiftoolStatus.local.resolved_path
				? String(this.exiftoolStatus.local.resolved_path)
				: '';
			return resolvedPath.includes('/var/packages/AV_ImgData/') || resolvedPath.includes('/volume') && resolvedPath.includes('/AV_ImgData/');
		},
	},
	mounted() {
		this.loadConfig();
		this.loadExiftoolStatus();
	},
	methods: {
		escapeRegExp(value) {
			return String(value || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
		},
		createDefaultConfig() {
			return {
				files: {
					USE_EXIFTOOL: false,
					USE_EXIFTOOL_FOR_SIDECARS: false,
					PREFER_EXIFTOOL_FOR_CONTEXT: false,
					PATHEXIFTOOL: 'exiftool',
					IMAGE_EXTENSIONS: ['jpg', 'jpeg', 'tif', 'tiff', 'png', 'heic', 'heif', 'dng', 'cr2', 'cr3', 'nef', 'nrw', 'arw', 'orf', 'rw2', 'raf', 'pef'],
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
			const source = Array.isArray(value) ? value : String(value || '').split(',');
			const normalized = source
				.map((entry) => String(entry || '').trim().toLowerCase().replace(/^\./, ''))
				.filter((entry, index, arr) => entry && arr.indexOf(entry) === index);
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

			const imageExtensions = this.normalizeImageExtensions(files.IMAGE_EXTENSIONS, defaults.files.IMAGE_EXTENSIONS);

			return {
				...root,
				files: {
					...files,
					USE_EXIFTOOL: Boolean(files.USE_EXIFTOOL ?? defaults.files.USE_EXIFTOOL),
					USE_EXIFTOOL_FOR_SIDECARS: Boolean(files.USE_EXIFTOOL_FOR_SIDECARS ?? defaults.files.USE_EXIFTOOL_FOR_SIDECARS),
					PREFER_EXIFTOOL_FOR_CONTEXT: Boolean(files.PREFER_EXIFTOOL_FOR_CONTEXT ?? defaults.files.PREFER_EXIFTOOL_FOR_CONTEXT),
					PATHEXIFTOOL: String(files.PATHEXIFTOOL || defaults.files.PATHEXIFTOOL),
					IMAGE_EXTENSIONS: imageExtensions,
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
			};
		},
		applyDefaults() {
			this.configModel = this.createDefaultConfig();
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
		async loadExiftoolStatus() {
			try {
				const data = await this.callApi('/webman/3rdparty/AV_ImgData/index.cgi/api/exiftool_status');
				this.exiftoolStatus = (data && data.data && typeof data.data === 'object') ? data.data : {};
			} catch (err) {
				this.exiftoolStatus = {};
			}
		},
		async installExiftool() {
			this.exiftoolInstalling = true;
			this.message = '';
			try {
				const data = await this.callApi('/webman/3rdparty/AV_ImgData/index.cgi/api/exiftool_install');
				const installedPath = data && data.data && data.data.installed_path ? data.data.installed_path : '';
				if (installedPath) {
					this.configModel.files.PATHEXIFTOOL = installedPath;
					this.configModel.files.USE_EXIFTOOL = true;
				}
				await this.loadExiftoolStatus();
				this.message = this.$t('config:message_exiftool_installed', 'ExifTool downloaded and installed.');
			} catch (err) {
				const detail = String(err.message || '');
				if (detail.includes('perl_not_available')) {
					this.message = this.$t(
						'config:error_exiftool_perl_required',
						'ExifTool cannot be installed because Perl is not available. Please install the Synology Perl package first.'
					);
				} else if (detail.includes('installed_exiftool_smoke_test_failed')) {
					this.message = this.$t(
						'config:error_exiftool_smoke_test_failed',
						'ExifTool was downloaded, but the installation test failed. ExifTool remains disabled.'
					);
				} else {
					this.message = `Error: ${detail}`;
				}
			} finally {
				this.exiftoolInstalling = false;
			}
		},
		async removeExiftool() {
			this.exiftoolRemoving = true;
			this.message = '';
			try {
				await this.callApi('/webman/3rdparty/AV_ImgData/index.cgi/api/exiftool_remove');
				this.configModel.files.PATHEXIFTOOL = 'exiftool';
				this.configModel.files.USE_EXIFTOOL = false;
				await this.loadExiftoolStatus();
				this.message = this.$t('config:message_exiftool_removed', 'ExifTool installation removed.');
			} catch (err) {
				this.message = `Error: ${err.message}`;
			} finally {
				this.exiftoolRemoving = false;
			}
		},
	},
};
</script>
