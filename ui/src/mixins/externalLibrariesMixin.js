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
			insightFaceStatus: {},
			imageBackendStatus: {},
			insightFaceStatusLoading: false,
			insightFaceModelDeleting: '',
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
				{ value: 'same_dir_stem', label: this.$avt('config:label_sidecar_variant_same_dir_stem', 'Same folder: image.xmp') },
				{ value: 'same_dir_filename', label: this.$avt('config:label_sidecar_variant_same_dir_filename', 'Same folder: image.jpg.xmp') },
				{ value: 'xmp_dir_stem', label: this.$avt('config:label_sidecar_variant_xmp_dir_stem', 'xmp subfolder: xmp/image.xmp') },
				{ value: 'xmp_dir_filename', label: this.$avt('config:label_sidecar_variant_xmp_dir_filename', 'xmp subfolder: xmp/image.jpg.xmp') },
			];
		},
		externalLibrariesSidecarReadModeOptions() {
			return [
				{ value: 'direct_only', label: this.$avt('config:sidecar_read_mode_direct_only', 'Direct reader only') },
				{ value: 'direct_first', label: this.$avt('config:sidecar_read_mode_direct_first', 'Direct reader, ExifTool fallback') },
				{ value: 'exiftool_first', label: this.$avt('config:sidecar_read_mode_exiftool_first', 'ExifTool first, direct fallback') },
				{ value: 'exiftool_only', label: this.$avt('config:sidecar_read_mode_exiftool_only', 'ExifTool only') },
			];
		},
		isExiftoolEnabled() {
			return !!(this.externalLibrariesConfigModel.files && this.externalLibrariesConfigModel.files.USE_EXIFTOOL);
		},
		canConfigureExiftoolReadOptions() {
			return this.isExiftoolEnabled;
		},
		canConfigureExiftoolPersistentMode() {
			return this.isExiftoolEnabled;
		},
		canConfigureManualExiftoolPath() {
			return !!(this.externalLibrariesConfigModel.files && this.externalLibrariesConfigModel.files.USE_MANUAL_PATHEXIFTOOL);
		},
		canConfigureExiftoolExtensions() {
			return this.isExiftoolEnabled;
		},
		insightFaceRuntimeStatus() {
			const status = this.insightFaceStatus && typeof this.insightFaceStatus === 'object'
				? this.insightFaceStatus
				: {};
			return status.insightface && typeof status.insightface === 'object' ? status.insightface : {};
		},
		insightFaceModelStatus() {
			const status = this.insightFaceRuntimeStatus && typeof this.insightFaceRuntimeStatus.model_status === 'object'
				? this.insightFaceRuntimeStatus.model_status
				: {};
			return {
				root: String(status.root || ''),
				model_store: String(status.model_store || ''),
				models: Array.isArray(status.models) ? status.models : [],
			};
		},
		insightFaceActiveModelName() {
			return String(this.insightFaceRuntimeStatus.active_model_name || '').trim();
		},
		insightFaceInstalledModelNames() {
			return this.insightFaceModelStatus.models
				.map((modelStatus) => String(modelStatus && modelStatus.name || '').trim())
				.filter((name, index, names) => name && names.indexOf(name) === index)
				.sort((left, right) => left.localeCompare(right));
		},
		imageProcessorVipsStatus() {
			const imageProcessors = this.imageBackendStatus && this.imageBackendStatus.image_processors && typeof this.imageBackendStatus.image_processors === 'object'
				? this.imageBackendStatus.image_processors
				: {};
			if (imageProcessors.IMAGE_PROCESSOR_VIPS && typeof imageProcessors.IMAGE_PROCESSOR_VIPS === 'object') {
				return imageProcessors.IMAGE_PROCESSOR_VIPS;
			}
			const nativeProcessors = this.insightFaceStatus && this.insightFaceStatus.native_processors && typeof this.insightFaceStatus.native_processors === 'object'
				? this.insightFaceStatus.native_processors
				: {};
			return nativeProcessors.IMAGE_PROCESSOR_VIPS && typeof nativeProcessors.IMAGE_PROCESSOR_VIPS === 'object'
				? nativeProcessors.IMAGE_PROCESSOR_VIPS
				: {};
		},
	},
	methods: {
		createExternalLibrariesDefaultConfig() {
			return {
				files: {
					USE_EXIFTOOL: false,
					CHECK_EXIFTOOL_UPDATES: true,
					USE_EXIFTOOL_FOR_SIDECARS: false,
					SIDECAR_EXIFTOOL_FALLBACK_ENABLED: false,
					SIDECAR_READ_MODE: 'direct_only',
					PREFER_EXIFTOOL_FOR_CONTEXT: false,
					EMBEDDED_XMP_FULL_SCAN_ENABLED: false,
					EXIFTOOL_PERSISTENT_ENABLED: true,
					EXIFTOOL_PERSISTENT_TIMEOUT_SECONDS: 30,
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
						RECOGNITION_SAFE_SCORE: 0.55,
						RECOGNITION_REVIEW_SCORE: 0.45,
						RECOGNITION_MIN_MARGIN: 0.08,
						RECOGNITION_OUTLIER_SIMILARITY_THRESHOLD: 0.35,
						RECOGNITION_DET_THRESH: 0.5,
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
				},
				face_match: {
					FILE_MATCH_SOURCE_SCOPE: 'both',
					PERSON_SORT_ORDER: 'id_desc',
				},
				native_processors: {
					FACE_PROCESSOR: {
						MODEL_ROOT: '',
						MODEL_NAME: '',
						TIMEOUT_SECONDS: 120,
						MAX_IMAGE_BYTES: 67108864,
						INSIGHTFACE_LICENSE_ACKNOWLEDGED: false,
					},
					IMAGE_PROCESSOR_VIPS: {
						ENABLED: false,
						PREFERRED: true,
						PATH: 'bin/av-imgdata-image-processor',
						TIMEOUT_SECONDS: 120,
						MAX_IMAGE_BYTES: 268435456,
						SUPPORTED_FORMATS: ['jpeg', 'jpg', 'png', 'webp', 'tiff'],
						ALLOW_FALLBACK_TO_DEFAULT: true,
					},
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
		normalizeExternalLibrariesSidecarReadMode(value, files = {}) {
			const normalized = String(value || '').trim().toLowerCase();
			if (['direct_only', 'direct_first', 'exiftool_first', 'exiftool_only'].includes(normalized)) {
				return normalized;
			}
			const useExiftool = Boolean(files && files.USE_EXIFTOOL_FOR_SIDECARS);
			const fallback = Boolean(files && files.SIDECAR_EXIFTOOL_FALLBACK_ENABLED);
			if (useExiftool && fallback) {
				return 'exiftool_first';
			}
			if (useExiftool) {
				return 'exiftool_only';
			}
			if (fallback) {
				return 'direct_first';
			}
			return 'direct_only';
		},
		getExternalLibrariesSidecarModeFlags(mode) {
			const normalized = this.normalizeExternalLibrariesSidecarReadMode(mode);
			return {
				USE_EXIFTOOL_FOR_SIDECARS: ['exiftool_first', 'exiftool_only'].includes(normalized),
				SIDECAR_EXIFTOOL_FALLBACK_ENABLED: ['direct_first', 'exiftool_first'].includes(normalized),
			};
		},
		normalizeExternalLibrariesChecksSingleSourceOfTruth(value, fallback = '') {
			const normalized = String(value || '').trim().toLowerCase();
			if (normalized === 'photos') {
				return normalized;
			}
			const parts = normalized.split(':');
			const metadataFormats = ['acd', 'microsoft', 'mwg_regions'];
			const metadataLocations = ['any', 'embedded', 'sidecar'];
			return (
				parts.length === 3
				&& parts[0] === 'metadata'
				&& metadataFormats.includes(parts[1])
				&& metadataLocations.includes(parts[2])
			) ? normalized : fallback;
		},
		clampExternalLibrariesNumber(value, min, max, fallback) {
			const numeric = Number(value);
			if (!Number.isFinite(numeric)) {
				return fallback;
			}
			return Math.max(min, Math.min(max, numeric));
		},
		formatExternalLibrariesImageExtensionsMultiline(value) {
			return this.normalizeExternalLibrariesImageExtensions(value, []).join(',\n');
		},
		setExternalLibrariesSidecarReadMode(mode) {
			const normalizedMode = this.normalizeExternalLibrariesSidecarReadMode(mode);
			const flags = this.getExternalLibrariesSidecarModeFlags(normalizedMode);
			this.externalLibrariesConfigModel = {
				...this.externalLibrariesConfigModel,
				files: {
					...this.externalLibrariesConfigModel.files,
					SIDECAR_READ_MODE: normalizedMode,
					...flags,
				},
			};
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
		setExternalLibrariesNativeProcessorConfigValue(processorKey, key, value) {
			const nativeProcessors = this.externalLibrariesConfigModel.native_processors || {};
			const processorConfig = nativeProcessors[processorKey] || {};
			const wasLicenseAcknowledged = processorKey === 'FACE_PROCESSOR' && key === 'INSIGHTFACE_LICENSE_ACKNOWLEDGED' && Boolean(processorConfig.INSIGHTFACE_LICENSE_ACKNOWLEDGED);
			this.externalLibrariesConfigModel = {
				...this.externalLibrariesConfigModel,
				native_processors: {
					...nativeProcessors,
					[processorKey]: {
						...processorConfig,
						[key]: value,
					},
				},
			};
			if (processorKey === 'FACE_PROCESSOR' && key === 'INSIGHTFACE_LICENSE_ACKNOWLEDGED' && Boolean(value) && !wasLicenseAcknowledged) {
				this.showExternalLibrariesRestartPopup(
					this.$avt(
						'config:popup_insightface_model_license_warning',
						'InsightFace can download models with separate non-free license terms. These models may only be used under the applicable InsightFace model license terms. Please review the InsightFace license notes before enabling this feature:\n\nhttps://github.com/deepinsight/insightface#license'
					)
				);
			}
		},
		getInsightFaceModelStatusLabel(modelStatus) {
			if (!modelStatus || typeof modelStatus !== 'object') {
				return this.$avt('status:not_available', 'Not available');
			}
			if (modelStatus.installed) {
				const fileCount = Array.isArray(modelStatus.onnx_files) ? modelStatus.onnx_files.length : 0;
				return this.$avt('config:insightface_model_installed', 'Installed ({count} ONNX files)', { count: fileCount });
			}
			return this.$avt('status:not_installed', 'Not installed');
		},
		formatInsightFaceNativeProcessorReason(reason) {
				const normalized = String(reason || '').trim().toLowerCase();
				const labels = {
					insightface_license_not_acknowledged: ['status:native_face_processor_reason_license_not_acknowledged', 'InsightFace model license terms have not been acknowledged.'],
					binary_missing: ['status:native_face_processor_reason_binary_missing', 'Native face processor binary is missing.'],
				binary_not_executable: ['status:native_face_processor_reason_binary_not_executable', 'Native face processor binary is not executable.'],
				version_failed: ['status:native_face_processor_reason_version_failed', 'Native face processor version check failed.'],
				probe_failed: ['status:native_face_processor_reason_probe_failed', 'Native face processor model probe failed.'],
				skeleton_no_inference: ['status:native_face_processor_reason_skeleton_no_inference', 'Native face processor skeleton does not run inference.'],
				onnxruntime_smoke_only: ['status:native_face_processor_reason_onnxruntime_smoke_only', 'ONNXRuntime smoke backend is available, but full inference is not ready.'],
				ready: ['status:native_face_processor_reason_ready', 'Native face processor is ready.'],
				unknown: ['status:native_face_processor_reason_unknown', 'Native face processor status is unknown.'],
			};
			const entry = labels[normalized];
			if (entry) {
				return this.$avt(entry[0], entry[1]);
			}
			return normalized || this.$avt('status:not_available', 'Not available');
		},
		formatImageProcessorVipsReason(reason) {
			const normalized = String(reason || '').trim().toLowerCase();
			const labels = {
				vips_disabled: ['status:vips_reason_disabled', 'libvips image backend is disabled.'],
				vips_binary_missing: ['status:vips_reason_binary_missing', 'libvips image processor binary is missing.'],
				vips_binary_not_executable: ['status:vips_reason_binary_not_executable', 'libvips image processor binary is not executable.'],
				vips_version_failed: ['status:vips_reason_version_failed', 'libvips image processor version check failed.'],
				vips_probe_failed: ['status:vips_reason_probe_failed', 'libvips image backend probe failed; default image backend is used.'],
				vips_format_unsupported: ['status:vips_reason_format_unsupported', 'Image format is not supported by the libvips backend.'],
				vips_ready: ['status:vips_reason_ready', 'libvips image backend is ready.'],
				vips_failed_fallback_used: ['status:vips_reason_failed_fallback_used', 'libvips failed; default image backend was used.'],
				vips_failed_no_fallback: ['status:vips_reason_failed_no_fallback', 'libvips failed and fallback is disabled.'],
			};
			const entry = labels[normalized];
			if (entry) {
				return this.$avt(entry[0], entry[1]);
			}
			return normalized || this.$avt('status:not_available', 'Not available');
		},
		showExternalLibrariesRestartPopup(message) {
			const text = String(message || '').trim();
			if (text) {
				window.alert(text);
			}
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
			const reviewIgnoreLists = (review.CHECKS_IGNORE_LISTS && typeof review.CHECKS_IGNORE_LISTS === 'object' && !Array.isArray(review.CHECKS_IGNORE_LISTS)) ? review.CHECKS_IGNORE_LISTS : {};
			const photos = (root.photos && typeof root.photos === 'object' && !Array.isArray(root.photos)) ? root.photos : {};
			const faceMatch = (root.face_match && typeof root.face_match === 'object' && !Array.isArray(root.face_match)) ? root.face_match : {};
			const nativeProcessors = (root.native_processors && typeof root.native_processors === 'object' && !Array.isArray(root.native_processors)) ? root.native_processors : {};
			const faceProcessor = (nativeProcessors.FACE_PROCESSOR && typeof nativeProcessors.FACE_PROCESSOR === 'object' && !Array.isArray(nativeProcessors.FACE_PROCESSOR)) ? nativeProcessors.FACE_PROCESSOR : {};
			const imageProcessorVips = (nativeProcessors.IMAGE_PROCESSOR_VIPS && typeof nativeProcessors.IMAGE_PROCESSOR_VIPS === 'object' && !Array.isArray(nativeProcessors.IMAGE_PROCESSOR_VIPS)) ? nativeProcessors.IMAGE_PROCESSOR_VIPS : {};

			const imageExtensions = this.normalizeExternalLibrariesImageExtensions(files.IMAGE_EXTENSIONS, defaults.files.IMAGE_EXTENSIONS);
			const exiftoolImageExtensions = this.normalizeExternalLibrariesImageExtensions(files.EXIFTOOL_IMAGE_EXTENSIONS, []);
			const sidecarReadMode = this.normalizeExternalLibrariesSidecarReadMode(files.SIDECAR_READ_MODE, files);
			const sidecarModeFlags = this.getExternalLibrariesSidecarModeFlags(sidecarReadMode);
			const persistentTimeoutSeconds = Math.max(1, Math.min(300, Number(files.EXIFTOOL_PERSISTENT_TIMEOUT_SECONDS) || defaults.files.EXIFTOOL_PERSISTENT_TIMEOUT_SECONDS));
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
					USE_EXIFTOOL_FOR_SIDECARS: sidecarModeFlags.USE_EXIFTOOL_FOR_SIDECARS,
					SIDECAR_EXIFTOOL_FALLBACK_ENABLED: sidecarModeFlags.SIDECAR_EXIFTOOL_FALLBACK_ENABLED,
					SIDECAR_READ_MODE: sidecarReadMode,
					PREFER_EXIFTOOL_FOR_CONTEXT: Boolean(files.PREFER_EXIFTOOL_FOR_CONTEXT ?? defaults.files.PREFER_EXIFTOOL_FOR_CONTEXT),
					EMBEDDED_XMP_FULL_SCAN_ENABLED: Boolean(files.EMBEDDED_XMP_FULL_SCAN_ENABLED ?? defaults.files.EMBEDDED_XMP_FULL_SCAN_ENABLED),
					EXIFTOOL_PERSISTENT_ENABLED: Boolean(files.EXIFTOOL_PERSISTENT_ENABLED ?? defaults.files.EXIFTOOL_PERSISTENT_ENABLED),
					EXIFTOOL_PERSISTENT_TIMEOUT_SECONDS: persistentTimeoutSeconds,
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
						RECOGNITION_SAFE_SCORE: this.clampExternalLibrariesNumber(checks.RECOGNITION_SAFE_SCORE, 0, 1, defaults.analysis.CHECKS.RECOGNITION_SAFE_SCORE),
						RECOGNITION_REVIEW_SCORE: this.clampExternalLibrariesNumber(checks.RECOGNITION_REVIEW_SCORE, 0, 1, defaults.analysis.CHECKS.RECOGNITION_REVIEW_SCORE),
						RECOGNITION_MIN_MARGIN: this.clampExternalLibrariesNumber(checks.RECOGNITION_MIN_MARGIN, 0, 1, defaults.analysis.CHECKS.RECOGNITION_MIN_MARGIN),
						RECOGNITION_OUTLIER_SIMILARITY_THRESHOLD: this.clampExternalLibrariesNumber(checks.RECOGNITION_OUTLIER_SIMILARITY_THRESHOLD, 0, 1, defaults.analysis.CHECKS.RECOGNITION_OUTLIER_SIMILARITY_THRESHOLD),
						RECOGNITION_DET_THRESH: this.clampExternalLibrariesNumber(checks.RECOGNITION_DET_THRESH, 0, 1, defaults.analysis.CHECKS.RECOGNITION_DET_THRESH),
						SINGLE_SOURCE_OF_TRUTH: this.normalizeExternalLibrariesChecksSingleSourceOfTruth(
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
				native_processors: {
					...nativeProcessors,
					FACE_PROCESSOR: {
						...faceProcessor,
						MODEL_ROOT: String(faceProcessor.MODEL_ROOT || defaults.native_processors.FACE_PROCESSOR.MODEL_ROOT),
						MODEL_NAME: String(faceProcessor.MODEL_NAME || defaults.native_processors.FACE_PROCESSOR.MODEL_NAME),
						TIMEOUT_SECONDS: Math.max(1, Math.min(3600, Number(faceProcessor.TIMEOUT_SECONDS) || defaults.native_processors.FACE_PROCESSOR.TIMEOUT_SECONDS)),
						MAX_IMAGE_BYTES: Math.max(1048576, Math.min(1073741824, Number(faceProcessor.MAX_IMAGE_BYTES) || defaults.native_processors.FACE_PROCESSOR.MAX_IMAGE_BYTES)),
						INSIGHTFACE_LICENSE_ACKNOWLEDGED: Boolean(faceProcessor.INSIGHTFACE_LICENSE_ACKNOWLEDGED ?? defaults.native_processors.FACE_PROCESSOR.INSIGHTFACE_LICENSE_ACKNOWLEDGED),
					},
					IMAGE_PROCESSOR_VIPS: {
						...imageProcessorVips,
						ENABLED: Boolean(imageProcessorVips.ENABLED ?? defaults.native_processors.IMAGE_PROCESSOR_VIPS.ENABLED),
						PREFERRED: Boolean(imageProcessorVips.PREFERRED ?? defaults.native_processors.IMAGE_PROCESSOR_VIPS.PREFERRED),
						PATH: String(imageProcessorVips.PATH || defaults.native_processors.IMAGE_PROCESSOR_VIPS.PATH),
						TIMEOUT_SECONDS: Math.max(1, Math.min(3600, Number(imageProcessorVips.TIMEOUT_SECONDS) || defaults.native_processors.IMAGE_PROCESSOR_VIPS.TIMEOUT_SECONDS)),
						MAX_IMAGE_BYTES: Math.max(1048576, Math.min(1073741824, Number(imageProcessorVips.MAX_IMAGE_BYTES) || defaults.native_processors.IMAGE_PROCESSOR_VIPS.MAX_IMAGE_BYTES)),
						SUPPORTED_FORMATS: this.normalizeExternalLibrariesImageExtensions(imageProcessorVips.SUPPORTED_FORMATS, defaults.native_processors.IMAGE_PROCESSOR_VIPS.SUPPORTED_FORMATS),
						ALLOW_FALLBACK_TO_DEFAULT: Boolean(imageProcessorVips.ALLOW_FALLBACK_TO_DEFAULT ?? defaults.native_processors.IMAGE_PROCESSOR_VIPS.ALLOW_FALLBACK_TO_DEFAULT),
					},
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
					SIDECAR_EXIFTOOL_FALLBACK_ENABLED: defaults.files.SIDECAR_EXIFTOOL_FALLBACK_ENABLED,
					SIDECAR_READ_MODE: defaults.files.SIDECAR_READ_MODE,
					PREFER_EXIFTOOL_FOR_CONTEXT: defaults.files.PREFER_EXIFTOOL_FOR_CONTEXT,
					EMBEDDED_XMP_FULL_SCAN_ENABLED: defaults.files.EMBEDDED_XMP_FULL_SCAN_ENABLED,
					EXIFTOOL_PERSISTENT_ENABLED: defaults.files.EXIFTOOL_PERSISTENT_ENABLED,
					EXIFTOOL_PERSISTENT_TIMEOUT_SECONDS: defaults.files.EXIFTOOL_PERSISTENT_TIMEOUT_SECONDS,
					PATHEXIFTOOL: defaults.files.PATHEXIFTOOL,
					USE_MANUAL_PATHEXIFTOOL: defaults.files.USE_MANUAL_PATHEXIFTOOL,
					MANUAL_PATHEXIFTOOL: defaults.files.MANUAL_PATHEXIFTOOL,
					IMAGE_EXTENSIONS_NATIVE_ONLY: defaults.files.IMAGE_EXTENSIONS_NATIVE_ONLY,
					EXIFTOOL_IMAGE_EXTENSIONS: defaults.files.EXIFTOOL_IMAGE_EXTENSIONS,
				},
				native_processors: defaults.native_processors,
			});
			this.exiftoolImageExtensionsInput = this.formatExternalLibrariesImageExtensionsMultiline(this.externalLibrariesConfigModel.files.EXIFTOOL_IMAGE_EXTENSIONS);
			this.externalLibrariesMessage = this.$avt('config:output_defaults_applied', 'Default values loaded into the editor.');
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
				await this.fetchInsightFaceStatus();
				await this.fetchImageBackendStatus();
			} catch (err) {
				this.externalLibrariesMessage = `Error: ${err.message}`;
			} finally {
				this.externalLibrariesLoading = false;
			}
		},
		async fetchImageBackendStatus() {
			try {
				const data = await this.callFileAnalysisApi('/webman/3rdparty/AV_ImgData/index.cgi/api/image_backend_status', {}, { resume: false, requireSynoToken: false, timeoutMs: 120000 });
				this.imageBackendStatus = this.getResponseData(data);
			} catch (err) {
				this.imageBackendStatus = {};
			}
		},
		async fetchInsightFaceStatus() {
			this.insightFaceStatusLoading = true;
			try {
				const data = await this.callFileAnalysisApi('/webman/3rdparty/AV_ImgData/index.cgi/api/insightface_status', {}, { resume: false, requireSynoToken: false, timeoutMs: 120000 });
				this.insightFaceStatus = this.getResponseData(data);
			} catch (err) {
				this.externalLibrariesMessage = `Error: ${err.message}`;
			} finally {
				this.insightFaceStatusLoading = false;
			}
		},
		async deleteInsightFaceModel(modelName) {
			const normalizedName = String(modelName || '').trim();
			if (!normalizedName || this.insightFaceModelDeleting) {
				return;
			}
			this.insightFaceModelDeleting = normalizedName;
			this.externalLibrariesMessage = '';
			try {
				await this.callFileAnalysisApi('/webman/3rdparty/AV_ImgData/index.cgi/api/insightface_model_delete', {
					model_name: normalizedName,
				});
				this.externalLibrariesMessage = this.$avt('config:message_insightface_model_deleted', 'InsightFace model removed.');
				await this.fetchInsightFaceStatus();
			} catch (err) {
				this.externalLibrariesMessage = `Error: ${err.message}`;
			} finally {
				this.insightFaceModelDeleting = '';
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
				await this.fetchInsightFaceStatus();
				await this.fetchImageBackendStatus();
				this.externalLibrariesMessage = this.$avt('config:message_saved', 'Configuration saved.');
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
				this.externalLibrariesMessage = this.$avt('config:message_exiftool_extensions_loaded', 'ExifTool extensions loaded into the editor.');
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
					if (!this.externalLibrariesConfigModel.files.USE_MANUAL_PATHEXIFTOOL) {
						this.externalLibrariesConfigModel.files.PATHEXIFTOOL = installedPath;
					}
					this.externalLibrariesConfigModel.files.USE_EXIFTOOL = true;
				}
				await this.fetchExiftoolStatus();
				this.externalLibrariesMessage = this.$avt('config:message_exiftool_installed', 'ExifTool downloaded and installed.');
				this.showExternalLibrariesRestartPopup(
					this.$avt(
						'config:popup_restart_may_be_required_exiftool',
						'ExifTool was installed. A package restart may be required before the command is fully available.'
					)
				);
			} catch (err) {
				const detail = String(err.message || '');
				if (detail.includes('perl_not_available')) {
					this.externalLibrariesMessage = this.$avt(
						'config:error_exiftool_perl_required',
						'ExifTool cannot be installed because Perl is not available. Please install the Synology Perl package first.'
					);
				} else if (detail.includes('installed_exiftool_smoke_test_failed')) {
					this.externalLibrariesMessage = this.$avt(
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
				if (!this.externalLibrariesConfigModel.files.USE_MANUAL_PATHEXIFTOOL) {
					this.externalLibrariesConfigModel.files.PATHEXIFTOOL = 'exiftool';
					this.externalLibrariesConfigModel.files.USE_EXIFTOOL = false;
				}
				await this.fetchExiftoolStatus();
				this.externalLibrariesMessage = this.$avt('config:message_exiftool_removed', 'ExifTool installation removed.');
			} catch (err) {
				this.externalLibrariesMessage = `Error: ${err.message}`;
			} finally {
				this.exiftoolRemoving = false;
			}
		},
	},
};
