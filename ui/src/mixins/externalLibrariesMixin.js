export default {
	data() {
		return {
			externalLibrariesLoading: false,
			externalLibrariesSaving: false,
			externalLibrariesMessage: '',
			externalLibrariesConfigPath: '',
			externalLibrariesConfigModel: this.createExternalLibrariesDefaultConfig(),
			exiftoolImageExtensionsInput: '',
			exiftoolInstalling: false,
			exiftoolRemoving: false,
			exiftoolExtensionsLoading: false,
		};
	},
	computed: {
		hasUsableExiftool() {
			return !!(this.exiftoolStatus && this.exiftoolStatus.local && this.exiftoolStatus.local.found);
		},
		hasBundledExiftool() {
			const resolvedPath = this.exiftoolStatus && this.exiftoolStatus.local && this.exiftoolStatus.local.resolved_path
				? String(this.exiftoolStatus.local.resolved_path)
				: '';
			const configuredPath = this.exiftoolStatus && this.exiftoolStatus.configured_path
				? String(this.exiftoolStatus.configured_path)
				: '';
			const bundledInstallExists = !!(this.exiftoolStatus && this.exiftoolStatus.bundled_install_exists);
			const packagePath = resolvedPath || configuredPath;
			return bundledInstallExists || packagePath.includes('/var/packages/AV_ImgData/') || packagePath.includes('/volume') && packagePath.includes('/AV_ImgData/');
		},
		exiftoolDownloadSourceUrl() {
			const onlineUrl = this.exiftoolStatus && this.exiftoolStatus.online && this.exiftoolStatus.online.unix_download_url
				? String(this.exiftoolStatus.online.unix_download_url)
				: '';
			if (onlineUrl) {
				return onlineUrl;
			}
			return this.exiftoolStatus && this.exiftoolStatus.last_download_url
				? String(this.exiftoolStatus.last_download_url)
				: '';
		},
		externalLibrariesSidecarLookupOptions() {
			return [
				{ value: 'same_dir_stem', label: this.$t('config:label_sidecar_variant_same_dir_stem', 'Same folder: image.xmp') },
				{ value: 'same_dir_filename', label: this.$t('config:label_sidecar_variant_same_dir_filename', 'Same folder: image.jpg.xmp') },
				{ value: 'xmp_dir_stem', label: this.$t('config:label_sidecar_variant_xmp_dir_stem', 'xmp subfolder: xmp/image.xmp') },
				{ value: 'xmp_dir_filename', label: this.$t('config:label_sidecar_variant_xmp_dir_filename', 'xmp subfolder: xmp/image.jpg.xmp') },
			];
		},
	},
	methods: {
		createExternalLibrariesDefaultConfig() {
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
		normalizeExternalLibrariesImageExtensions(value, fallback = []) {
			const source = Array.isArray(value) ? value : String(value || '').split(/[\s,;]+/);
			const normalized = source
				.map((entry) => String(entry || '').trim().toLowerCase().replace(/^\./, ''))
				.filter((entry, index, arr) => entry && arr.indexOf(entry) === index);
			return normalized.length ? normalized : [...fallback];
		},
		normalizeExternalLibrariesSelectionList(value, allowedValues, fallback = []) {
			const source = Array.isArray(value) ? value : [];
			const allowed = Array.isArray(allowedValues) ? allowedValues : [];
			const normalized = source
				.map((entry) => String(entry || '').trim())
				.filter((entry, index, arr) => entry && allowed.includes(entry) && arr.indexOf(entry) === index);
			return normalized.length ? normalized : [...fallback];
		},
		formatExternalLibrariesImageExtensionsMultiline(value) {
			return this.normalizeExternalLibrariesImageExtensions(value, []).join(',\n');
		},
		setExternalLibrariesFileConfigValue(key, value) {
			this.externalLibrariesConfigModel = {
				...this.externalLibrariesConfigModel,
				files: {
					...this.externalLibrariesConfigModel.files,
					[key]: value,
				},
			};
		},
		setExiftoolImageExtensionsInput(value) {
			this.exiftoolImageExtensionsInput = String(value || '');
		},
		normalizeExternalLibrariesConfig(input) {
			const root = (input && typeof input === 'object' && !Array.isArray(input)) ? input : {};
			const defaults = this.createExternalLibrariesDefaultConfig();
			const files = (root.files && typeof root.files === 'object' && !Array.isArray(root.files)) ? root.files : {};
			const metadata = (root.metadata && typeof root.metadata === 'object' && !Array.isArray(root.metadata)) ? root.metadata : {};
			const schemas = (metadata.SCHEMAS && typeof metadata.SCHEMAS === 'object' && !Array.isArray(metadata.SCHEMAS)) ? metadata.SCHEMAS : {};
			const analysis = (root.analysis && typeof root.analysis === 'object' && !Array.isArray(root.analysis)) ? root.analysis : {};
			const checks = (analysis.CHECKS && typeof analysis.CHECKS === 'object' && !Array.isArray(analysis.CHECKS)) ? analysis.CHECKS : {};
			const review = (root.review && typeof root.review === 'object' && !Array.isArray(root.review)) ? root.review : {};
			const reviewOptions = (review.OPTIONS && typeof review.OPTIONS === 'object' && !Array.isArray(review.OPTIONS)) ? review.OPTIONS : {};
			const photos = (root.photos && typeof root.photos === 'object' && !Array.isArray(root.photos)) ? root.photos : {};
			const faceMatch = (root.face_match && typeof root.face_match === 'object' && !Array.isArray(root.face_match)) ? root.face_match : {};

			const imageExtensions = this.normalizeExternalLibrariesImageExtensions(files.IMAGE_EXTENSIONS, defaults.files.IMAGE_EXTENSIONS);
			const exiftoolImageExtensions = this.normalizeExternalLibrariesImageExtensions(files.EXIFTOOL_IMAGE_EXTENSIONS, []);
			const sidecarLookupVariants = this.normalizeExternalLibrariesSelectionList(
				files.SIDECAR_LOOKUP_VARIANTS,
				this.externalLibrariesSidecarLookupOptions.map((option) => option.value),
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
		applyExternalLibrariesDefaults() {
			const defaults = this.createExternalLibrariesDefaultConfig();
			this.externalLibrariesConfigModel = this.normalizeExternalLibrariesConfig({
				...this.externalLibrariesConfigModel,
				files: {
					...this.externalLibrariesConfigModel.files,
					USE_EXIFTOOL: defaults.files.USE_EXIFTOOL,
					CHECK_EXIFTOOL_UPDATES: defaults.files.CHECK_EXIFTOOL_UPDATES,
					USE_EXIFTOOL_FOR_SIDECARS: defaults.files.USE_EXIFTOOL_FOR_SIDECARS,
					PREFER_EXIFTOOL_FOR_CONTEXT: defaults.files.PREFER_EXIFTOOL_FOR_CONTEXT,
					PATHEXIFTOOL: defaults.files.PATHEXIFTOOL,
					IMAGE_EXTENSIONS_NATIVE_ONLY: defaults.files.IMAGE_EXTENSIONS_NATIVE_ONLY,
					EXIFTOOL_IMAGE_EXTENSIONS: defaults.files.EXIFTOOL_IMAGE_EXTENSIONS,
				},
			});
			this.exiftoolImageExtensionsInput = this.formatExternalLibrariesImageExtensionsMultiline(this.externalLibrariesConfigModel.files.EXIFTOOL_IMAGE_EXTENSIONS);
			this.externalLibrariesMessage = this.$t('config:output_defaults_applied', 'Default values loaded into the editor.');
		},
		async loadExternalLibrariesConfig() {
			this.externalLibrariesLoading = true;
			this.externalLibrariesMessage = '';
			try {
				const data = await this.callFileAnalysisApi('/webman/3rdparty/AV_ImgData/index.cgi/api/config_get');
				this.externalLibrariesConfigPath = (data && data.data && data.data.config_path) || '';
				this.externalLibrariesConfigModel = this.normalizeExternalLibrariesConfig(data && data.data && data.data.config);
				this.exiftoolImageExtensionsInput = this.formatExternalLibrariesImageExtensionsMultiline(this.externalLibrariesConfigModel.files.EXIFTOOL_IMAGE_EXTENSIONS);
				await this.fetchExiftoolStatus();
			} catch (err) {
				this.externalLibrariesMessage = `Error: ${err.message}`;
			} finally {
				this.externalLibrariesLoading = false;
			}
		},
		async saveExternalLibrariesConfig() {
			this.externalLibrariesSaving = true;
			this.externalLibrariesMessage = '';
			try {
				const payloadConfig = {
					...this.externalLibrariesConfigModel,
					files: {
						...this.externalLibrariesConfigModel.files,
						EXIFTOOL_IMAGE_EXTENSIONS: this.normalizeExternalLibrariesImageExtensions(this.exiftoolImageExtensionsInput, []),
					},
				};
				const normalized = this.normalizeExternalLibrariesConfig(payloadConfig);
				const data = await this.callFileAnalysisApi('/webman/3rdparty/AV_ImgData/index.cgi/api/config_save', { config: normalized });
				this.externalLibrariesConfigPath = (data && data.data && data.data.config_path) || this.externalLibrariesConfigPath;
				this.externalLibrariesConfigModel = this.normalizeExternalLibrariesConfig(data && data.data && data.data.config);
				this.exiftoolImageExtensionsInput = this.formatExternalLibrariesImageExtensionsMultiline(this.externalLibrariesConfigModel.files.EXIFTOOL_IMAGE_EXTENSIONS);
				await this.fetchExiftoolStatus();
				this.externalLibrariesMessage = this.$t('config:message_saved', 'Configuration saved.');
			} catch (err) {
				this.externalLibrariesMessage = `Error: ${err.message}`;
			} finally {
				this.externalLibrariesSaving = false;
			}
		},
		async loadExiftoolExtensions() {
			this.exiftoolExtensionsLoading = true;
			this.externalLibrariesMessage = '';
			try {
				const data = await this.callFileAnalysisApi('/webman/3rdparty/AV_ImgData/index.cgi/api/exiftool_extensions');
				const extensions = data && data.data && Array.isArray(data.data.extensions) ? data.data.extensions : [];
				this.exiftoolImageExtensionsInput = this.formatExternalLibrariesImageExtensionsMultiline(extensions);
				this.externalLibrariesMessage = this.$t('config:message_exiftool_extensions_loaded', 'ExifTool extensions loaded into the editor.');
			} catch (err) {
				this.externalLibrariesMessage = `Error: ${err.message}`;
			} finally {
				this.exiftoolExtensionsLoading = false;
			}
		},
		async installExiftool() {
			this.exiftoolInstalling = true;
			this.externalLibrariesMessage = '';
			try {
				const data = await this.callFileAnalysisApi('/webman/3rdparty/AV_ImgData/index.cgi/api/exiftool_install');
				const installedPath = data && data.data && data.data.configured_path ? data.data.configured_path : '';
				if (installedPath) {
					this.externalLibrariesConfigModel.files.PATHEXIFTOOL = installedPath;
					this.externalLibrariesConfigModel.files.USE_EXIFTOOL = true;
				}
				await this.fetchExiftoolStatus();
				this.externalLibrariesMessage = this.$t('config:message_exiftool_installed', 'ExifTool downloaded and installed.');
			} catch (err) {
				const detail = String(err.message || '');
				if (detail.includes('perl_not_available')) {
					this.externalLibrariesMessage = this.$t(
						'config:error_exiftool_perl_required',
						'ExifTool cannot be installed because Perl is not available. Please install the Synology Perl package first.'
					);
				} else if (detail.includes('installed_exiftool_smoke_test_failed')) {
					this.externalLibrariesMessage = this.$t(
						'config:error_exiftool_smoke_test_failed',
						'ExifTool was downloaded, but the installation test failed. ExifTool remains disabled.'
					);
				} else {
					this.externalLibrariesMessage = `Error: ${detail}`;
				}
			} finally {
				this.exiftoolInstalling = false;
			}
		},
		async removeExiftool() {
			this.exiftoolRemoving = true;
			this.externalLibrariesMessage = '';
			try {
				await this.callFileAnalysisApi('/webman/3rdparty/AV_ImgData/index.cgi/api/exiftool_remove');
				this.externalLibrariesConfigModel.files.PATHEXIFTOOL = 'exiftool';
				this.externalLibrariesConfigModel.files.USE_EXIFTOOL = false;
				await this.fetchExiftoolStatus();
				this.externalLibrariesMessage = this.$t('config:message_exiftool_removed', 'ExifTool installation removed.');
			} catch (err) {
				this.externalLibrariesMessage = `Error: ${err.message}`;
			} finally {
				this.exiftoolRemoving = false;
			}
		},
	},
};
