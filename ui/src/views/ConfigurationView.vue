<template>
	<section class="panel">
		<div class="panel-head">
			<h1>{{ $t('config:title', 'Configuration') }}</h1>
			<p>{{ $t('config:desc', 'Central area for runtime and package configuration.') }}</p>
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
					<label class="config-field">
						<span class="config-field-label">{{ $t('config:label_exiftool_path', 'ExifTool path') }}</span>
						<input
							v-model="configModel.files.PATHEXIFTOOL"
							type="text"
							class="config-text-input"
							:disabled="saving"
							:placeholder="$t('config:placeholder_exiftool_path', 'exiftool')"
						/>
					</label>

					<label class="config-checkbox">
						<input v-model="configModel.files.USE_EXIFTOOL" type="checkbox" :disabled="saving" />
						<span>{{ $t('config:label_use_exiftool', 'Use ExifTool for embedded XMP') }}</span>
					</label>

					<label class="config-checkbox">
						<input v-model="configModel.metadata.SCHEMAS.ACD" type="checkbox" :disabled="saving" />
						<span>{{ $t('config:label_schema_acd', 'Read ACDSee metadata') }}</span>
					</label>

					<label class="config-checkbox">
						<input v-model="configModel.metadata.SCHEMAS.PICASA" type="checkbox" :disabled="saving" />
						<span>{{ $t('config:label_schema_picasa', 'Read MWG/Picasa face metadata') }}</span>
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
	mounted() {
		this.loadConfig();
	},
	methods: {
		createDefaultConfig() {
			return {
				files: {
					USE_EXIFTOOL: false,
					PATHEXIFTOOL: 'exiftool',
					IMAGE_EXTENSIONS: ['jpg', 'jpeg', 'tif', 'tiff', 'png', 'heic', 'heif', 'dng', 'cr2', 'cr3', 'nef', 'nrw', 'arw', 'orf', 'rw2', 'raf', 'pef'],
				},
				metadata: {
					SCHEMAS: {
						ACD: true,
						PICASA: true,
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
			const match = document.cookie.match(new RegExp('(?:^|; )' + name.replace(/[.$?*|{}()\[\]\\/+^]/g, '\\$&') + '=([^;]*)'));
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
		normalizeConfig(input) {
			const root = (input && typeof input === 'object' && !Array.isArray(input)) ? input : {};
			const defaults = this.createDefaultConfig();
			const files = (root.files && typeof root.files === 'object' && !Array.isArray(root.files)) ? root.files : {};
			const metadata = (root.metadata && typeof root.metadata === 'object' && !Array.isArray(root.metadata)) ? root.metadata : {};
			const schemas = (metadata.SCHEMAS && typeof metadata.SCHEMAS === 'object' && !Array.isArray(metadata.SCHEMAS)) ? metadata.SCHEMAS : {};
			const photos = (root.photos && typeof root.photos === 'object' && !Array.isArray(root.photos)) ? root.photos : {};

			const imageExtensions = this.normalizeImageExtensions(files.IMAGE_EXTENSIONS, defaults.files.IMAGE_EXTENSIONS);

			return {
				...root,
				files: {
					...files,
					USE_EXIFTOOL: Boolean(files.USE_EXIFTOOL ?? defaults.files.USE_EXIFTOOL),
					PATHEXIFTOOL: String(files.PATHEXIFTOOL || defaults.files.PATHEXIFTOOL),
					IMAGE_EXTENSIONS: imageExtensions,
				},
				metadata: {
					...metadata,
					SCHEMAS: {
						...schemas,
						ACD: Boolean(schemas.ACD ?? defaults.metadata.SCHEMAS.ACD),
						PICASA: Boolean(schemas.PICASA ?? defaults.metadata.SCHEMAS.PICASA),
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
				const resp = await fetch('/webman/3rdparty/AV_ImgData/index.cgi/api/config_get', {
					method: 'POST',
					credentials: 'include',
					headers: {
						'Content-Type': 'application/json',
						'X-SYNO-TOKEN': this.getSynoToken(),
					},
					body: JSON.stringify({
						cookies: this.collectDsmCookies(),
						synoToken: this.getSynoToken(),
					}),
				});
				const data = await resp.json().catch(() => ({}));
				if (!resp.ok || data.success === false) {
					const backendError = data.error || `HTTP ${resp.status}`;
					throw new Error(typeof backendError === 'string' ? backendError : JSON.stringify(backendError));
				}
				this.configPath = (data && data.data && data.data.config_path) || '';
				this.configModel = this.normalizeConfig(data && data.data && data.data.config);
				this.imageExtensionsInput = this.formatImageExtensions(this.configModel.files.IMAGE_EXTENSIONS);
				this.message = this.$t('config:message_loaded', 'Configuration loaded.');
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
				const resp = await fetch('/webman/3rdparty/AV_ImgData/index.cgi/api/config_save', {
					method: 'POST',
					credentials: 'include',
					headers: {
						'Content-Type': 'application/json',
						'X-SYNO-TOKEN': this.getSynoToken(),
					},
					body: JSON.stringify({
						config: normalized,
						cookies: this.collectDsmCookies(),
						synoToken: this.getSynoToken(),
					}),
				});
				const data = await resp.json().catch(() => ({}));
				if (!resp.ok || data.success === false) {
					const backendError = data.error || `HTTP ${resp.status}`;
					throw new Error(typeof backendError === 'string' ? backendError : JSON.stringify(backendError));
				}
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
