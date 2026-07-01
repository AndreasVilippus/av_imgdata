<template>
	<section class="panel">
		<div class="panel-head">
			<div class="sm-section-title">{{ panelTitle }}</div>
			<p v-if="panelDescription">{{ panelDescription }}</p>
		</div>

		<div v-if="isEditableConfigView" class="config-actions config-actions-right">
			<v-button @click="vm.loadExternalLibrariesConfig" :disabled="vm.externalLibrariesLoading || vm.externalLibrariesSaving" style="width: 160px;">
				{{ vm.$avt('config:button_reload', 'Reload') }}
			</v-button>
			<v-button @click="vm.applyExternalLibrariesDefaults" :disabled="vm.externalLibrariesLoading || vm.externalLibrariesSaving" style="width: 160px;">
				{{ vm.$avt('config:button_defaults', 'Defaults') }}
			</v-button>
			<v-button @click="vm.saveExternalLibrariesConfig" :disabled="vm.externalLibrariesLoading || vm.externalLibrariesSaving" style="width: 160px;">
				{{ vm.$avt('config:button_save', 'Save') }}
			</v-button>
		</div>

		<div v-if="vm.externalLibrariesMessage" class="config-message">{{ vm.externalLibrariesMessage }}</div>

		<div v-if="vm.externalLibrariesLoading" class="config-loading">
			<span class="sm-loader"></span>
			{{ vm.$avt('config:loading', 'Loading configuration...') }}
		</div>

		<div v-else class="config-layout">
			<section v-if="isExternalLibrariesInfoView" class="config-card">
				<div class="sm-section-title">{{ vm.$avt('status:exiftool_title', 'ExifTool') }}</div>
				<div class="sm-kv-list">
					<div class="sm-kv-row">
						<div class="sm-kv-key">{{ vm.$avt('status:exiftool_found', 'Found') }}</div>
						<div class="sm-kv-value">{{ vm.hasLocalExiftool ? vm.$avt('status:yes', 'Yes') : vm.$avt('status:no', 'No') }}</div>
					</div>
					<div class="sm-kv-row">
						<div class="sm-kv-key">{{ vm.$avt('status:exiftool_configured_path', 'Configured path') }}</div>
						<div class="sm-kv-value">{{ vm.exiftoolStatus.configured_path || vm.$avt('status:not_available', 'Not available') }}</div>
					</div>
					<template v-if="vm.hasLocalExiftool">
						<div class="sm-kv-row">
							<div class="sm-kv-key">{{ vm.$avt('status:exiftool_local_version', 'Local version') }}</div>
							<div class="sm-kv-value">{{ vm.exiftoolStatus.local && vm.exiftoolStatus.local.version || vm.$avt('status:not_available', 'Not available') }}</div>
						</div>
						<div class="sm-kv-row">
							<div class="sm-kv-key">{{ vm.$avt('status:exiftool_latest_version', 'Latest official version') }}</div>
							<div class="sm-kv-value">{{ vm.exiftoolStatus.online && vm.exiftoolStatus.online.latest_version || vm.$avt('status:not_available', 'Not available') }}</div>
						</div>
						<div class="sm-kv-row">
							<div class="sm-kv-key">{{ vm.$avt('status:exiftool_update_available', 'Update available') }}</div>
							<div class="sm-kv-value">{{ vm.exiftoolStatus.update_available ? vm.$avt('status:yes', 'Yes') : vm.$avt('status:no', 'No') }}</div>
						</div>
						<div class="sm-kv-row">
							<div class="sm-kv-key">{{ vm.$avt('status:exiftool_resolved_path', 'Resolved path') }}</div>
							<div class="sm-kv-value">{{ vm.exiftoolStatus.local && vm.exiftoolStatus.local.resolved_path || vm.$avt('status:not_available', 'Not available') }}</div>
						</div>
					</template>
				</div>
			</section>

			<section v-if="isExternalLibrariesInfoView" class="config-card">
				<div class="sm-section-title">{{ vm.$avt('nav:pip_packages', 'pip packages') }}</div>
				<div class="sm-kv-list">
					<div class="sm-kv-row">
						<div class="sm-kv-key">{{ vm.$avt('config:label_pip_package_status', 'InsightFace status') }}</div>
						<div class="sm-kv-value">
							{{ vm.insightFacePipPackageStatus.installed ? vm.$avt('status:installed', 'Installed') : vm.$avt('status:not_installed', 'Not installed') }}
						</div>
					</div>
					<div class="sm-kv-row">
						<div class="sm-kv-key">{{ vm.$avt('config:label_pip_package_enabled', 'Enabled in config') }}</div>
						<div class="sm-kv-value">
							{{ vm.insightFacePipPackageStatus.enabled ? vm.$avt('status:yes', 'Yes') : vm.$avt('status:no', 'No') }}
						</div>
					</div>
					<div class="sm-kv-row">
						<div class="sm-kv-key">{{ vm.$avt('config:label_pip_last_install_status', 'Last install status') }}</div>
						<div class="sm-kv-value">
							{{ vm.getPipPackageInstallStatusLabel(vm.insightFacePipPackageStatus.install_status) }}
						</div>
					</div>
					<div v-if="vm.insightFacePipPackageStatus.install_status && vm.insightFacePipPackageStatus.install_status.message" class="sm-kv-row">
						<div class="sm-kv-key">{{ vm.$avt('config:label_pip_last_install_message', 'Last install message') }}</div>
						<div class="sm-kv-value">{{ vm.insightFacePipPackageStatus.install_status.message }}</div>
					</div>
					<div v-if="vm.insightFaceModelStatus.root" class="sm-kv-row">
						<div class="sm-kv-key">{{ vm.$avt('config:label_insightface_model_root', 'InsightFace model root') }}</div>
						<div class="sm-kv-value">{{ vm.insightFaceModelStatus.root }}</div>
					</div>
					<div v-if="vm.insightFaceModelStatus.model_store" class="sm-kv-row">
						<div class="sm-kv-key">{{ vm.$avt('config:label_insightface_model_store', 'InsightFace model store') }}</div>
						<div class="sm-kv-value">{{ vm.insightFaceModelStatus.model_store }}</div>
					</div>
					<template v-if="Array.isArray(vm.insightFacePipPackageStatus.modules)">
						<div
							v-for="moduleStatus in vm.insightFacePipPackageStatus.modules"
							:key="moduleStatus.package"
							class="sm-kv-row"
						>
							<div class="sm-kv-key">{{ moduleStatus.package }}</div>
							<div class="sm-kv-value">
								{{ vm.getPipPackageModuleStatusLabel(moduleStatus) }}
							</div>
						</div>
					</template>
					<div v-if="Array.isArray(vm.insightFacePipPackageStatus.conflicts) && vm.insightFacePipPackageStatus.conflicts.length" class="sm-kv-row">
						<div class="sm-kv-key">{{ vm.$avt('config:label_pip_conflicts', 'Package conflicts') }}</div>
						<div class="sm-kv-value">
							{{ vm.insightFacePipPackageStatus.conflicts.map((item) => `${item.package} ${item.version}`).join(', ') }}
						</div>
					</div>
					<template v-if="Array.isArray(vm.insightFaceModelStatus.models) && vm.insightFaceModelStatus.models.length">
						<div
							v-for="modelStatus in vm.insightFaceModelStatus.models"
							:key="`info-model-${modelStatus.name}`"
							class="sm-kv-row"
						>
							<div class="sm-kv-key">{{ vm.$avt('config:label_insightface_model', 'Model') }}: {{ modelStatus.name }}</div>
							<div class="sm-kv-value">{{ vm.getInsightFaceModelStatusLabel(modelStatus) }}</div>
						</div>
					</template>
				</div>
			</section>

			<section v-if="isExiftoolConfigView" class="config-card">
				<div class="config-form-grid">
					<div class="sm-section-title">{{ vm.$avt('config:exiftool_group_activation', 'ExifTool activation and path') }}</div>

					<label class="config-checkbox">
						<input
							:checked="vm.externalLibrariesConfigModel.files.USE_EXIFTOOL"
							type="checkbox"
							:disabled="vm.externalLibrariesSaving"
							@change="vm.setExternalLibrariesFileConfigValue('USE_EXIFTOOL', $event.target.checked)"
						/>
						<span>{{ vm.$avt('config:label_use_exiftool', 'Use ExifTool for metadata reading') }}</span>
					</label>

					<div class="config-card-desc">
						{{ vm.hasUsableExiftool
							? vm.$avt('config:hint_exiftool_available', 'ExifTool is available.')
							: vm.$avt('config:hint_exiftool_missing', 'ExifTool is not currently available. Install the bundled ExifTool or configure a manual path before enabling ExifTool-dependent readers.') }}
					</div>

					<label class="config-checkbox">
						<input
							:checked="vm.externalLibrariesConfigModel.files.CHECK_EXIFTOOL_UPDATES"
							type="checkbox"
							:disabled="vm.externalLibrariesSaving"
							@change="vm.setExternalLibrariesFileConfigValue('CHECK_EXIFTOOL_UPDATES', $event.target.checked)"
						/>
						<span>{{ vm.$avt('config:label_check_exiftool_updates', 'Check for newer ExifTool versions') }}</span>
					</label>

					<label class="config-checkbox">
						<input
							:checked="vm.externalLibrariesConfigModel.files.USE_MANUAL_PATHEXIFTOOL"
							type="checkbox"
							:disabled="vm.externalLibrariesSaving"
							@change="vm.setExternalLibrariesFileConfigValue('USE_MANUAL_PATHEXIFTOOL', $event.target.checked)"
						/>
						<span>{{ vm.$avt('config:label_use_manual_exiftool_path', 'Use manual path to ExifTool') }}</span>
					</label>

					<label v-if="vm.canConfigureManualExiftoolPath" class="config-field">
						<span class="config-field-label">{{ vm.$avt('config:label_manual_exiftool_path', 'Path to ExifTool') }}</span>
						<input
							:value="vm.externalLibrariesConfigModel.files.MANUAL_PATHEXIFTOOL"
							type="text"
							class="config-input"
							:disabled="vm.externalLibrariesSaving"
							:placeholder="vm.$avt('config:placeholder_manual_exiftool_path', '/usr/local/bin/exiftool')"
							@input="vm.setExternalLibrariesFileConfigValue('MANUAL_PATHEXIFTOOL', $event.target.value)"
						/>
						<span class="config-card-desc">
							{{ vm.$avt('config:hint_manual_exiftool_path', 'When enabled, this path is used instead of the bundled ExifTool path and is not changed by install or remove actions.') }}
						</span>
					</label>

					<div class="sm-section-title">{{ vm.$avt('config:exiftool_group_reading', 'ExifTool reading behavior') }}</div>

					<label class="config-field">
						<span class="config-field-label">{{ vm.$avt('config:label_sidecar_read_mode', 'XMP sidecar reading') }}</span>
						<select
							:value="vm.externalLibrariesConfigModel.files.SIDECAR_READ_MODE"
							class="config-input"
							:disabled="vm.externalLibrariesSaving || !vm.canConfigureExiftoolReadOptions"
							@change="vm.setExternalLibrariesSidecarReadMode($event.target.value)"
						>
							<option v-for="option in vm.externalLibrariesSidecarReadModeOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
						</select>
						<span class="config-card-desc">{{ vm.$avt('config:hint_sidecar_read_mode', 'This replaces the older overlapping sidecar checkboxes. Direct reading is fastest; ExifTool can be used first, only, or as fallback.') }}</span>
					</label>

					<label class="config-checkbox" :title="vm.$avt('config:hint_prefer_exiftool_for_context', 'Prefer ExifTool for bundled metadata context: embedded XMP, size and orientation. Face data is not read preferentially from ExifTool by this option.')">
						<input
							:checked="vm.externalLibrariesConfigModel.files.PREFER_EXIFTOOL_FOR_CONTEXT"
							type="checkbox"
							:disabled="vm.externalLibrariesSaving || !vm.canConfigureExiftoolReadOptions"
							@change="vm.setExternalLibrariesFileConfigValue('PREFER_EXIFTOOL_FOR_CONTEXT', $event.target.checked)"
						/>
						<span>{{ vm.$avt('config:label_prefer_exiftool_for_context', 'Prefer ExifTool for metadata (orientation, size, ...)') }}</span>
					</label>

					<label class="config-checkbox" :title="vm.$avt('config:hint_embedded_xmp_full_scan_enabled', 'Use the native embedded-XMP full scan as an extended fallback when ExifTool does not provide embedded XMP.')">
						<input
							:checked="vm.externalLibrariesConfigModel.files.EMBEDDED_XMP_FULL_SCAN_ENABLED"
							type="checkbox"
							:disabled="vm.externalLibrariesSaving"
							@change="vm.setExternalLibrariesFileConfigValue('EMBEDDED_XMP_FULL_SCAN_ENABLED', $event.target.checked)"
						/>
						<span>{{ vm.$avt('config:label_embedded_xmp_full_scan_enabled', 'Use native embedded-XMP full-scan fallback') }}</span>
					</label>

					<div class="sm-section-title">{{ vm.$avt('config:exiftool_group_process', 'ExifTool performance and process') }}</div>

					<label class="config-checkbox">
						<input
							:checked="vm.externalLibrariesConfigModel.files.EXIFTOOL_PERSISTENT_ENABLED"
							type="checkbox"
							:disabled="vm.externalLibrariesSaving || !vm.canConfigureExiftoolPersistentMode"
							@change="vm.setExternalLibrariesFileConfigValue('EXIFTOOL_PERSISTENT_ENABLED', $event.target.checked)"
						/>
						<span>{{ vm.$avt('config:label_exiftool_persistent_enabled', 'Use persistent ExifTool process for reads') }}</span>
					</label>
					<span class="config-card-desc">{{ vm.$avt('config:hint_exiftool_persistent_enabled', 'Read operations use one serialized ExifTool stay-open process. Write operations still use isolated one-shot ExifTool calls.') }}</span>

					<label v-if="vm.externalLibrariesConfigModel.files.EXIFTOOL_PERSISTENT_ENABLED" class="config-field">
						<span class="config-field-label">{{ vm.$avt('config:label_exiftool_persistent_timeout', 'Persistent ExifTool timeout in seconds') }}</span>
						<input
							:value="vm.externalLibrariesConfigModel.files.EXIFTOOL_PERSISTENT_TIMEOUT_SECONDS"
							type="number"
							min="1"
							max="300"
							class="config-input"
							:disabled="vm.externalLibrariesSaving || !vm.canConfigureExiftoolPersistentMode"
							@input="vm.setExternalLibrariesFileConfigValue('EXIFTOOL_PERSISTENT_TIMEOUT_SECONDS', Number($event.target.value) || 30)"
						/>
					</label>

					<div class="sm-section-title">{{ vm.$avt('config:exiftool_group_extensions', 'ExifTool file extensions') }}</div>

					<label class="config-checkbox" :title="vm.$avt('config:hint_image_extensions_native_only', 'If enabled, the general metadata scan extension list is only used by native readers. ExifTool uses its own extension list instead.')">
						<input
							:checked="vm.externalLibrariesConfigModel.files.IMAGE_EXTENSIONS_NATIVE_ONLY"
							type="checkbox"
							:disabled="vm.externalLibrariesSaving"
							@change="vm.setExternalLibrariesFileConfigValue('IMAGE_EXTENSIONS_NATIVE_ONLY', $event.target.checked)"
						/>
						<span>{{ vm.$avt('config:label_image_extensions_native_only', 'Use general file extensions only for native readers') }}</span>
					</label>

					<label class="config-field">
						<span class="config-field-label">{{ vm.$avt('config:label_exiftool_image_extensions', 'ExifTool file extensions for metadata scan') }}</span>
						<textarea
							:value="vm.exiftoolImageExtensionsInput"
							class="config-textarea"
							:disabled="vm.externalLibrariesSaving || vm.exiftoolExtensionsLoading || !vm.canConfigureExiftoolExtensions"
							:placeholder="vm.$avt('config:placeholder_exiftool_image_extensions', 'Leave empty to use all readable extensions reported by ExifTool.')"
							@input="vm.setExiftoolImageExtensionsInput($event.target.value)"
						></textarea>
						<span class="config-card-desc">{{ vm.$avt('config:hint_exiftool_image_extensions', 'When the field is empty, all readable ExifTool extensions are queried automatically.') }}</span>
						<div class="config-inline-actions">
							<v-button @click="vm.loadExiftoolExtensions" :disabled="vm.externalLibrariesSaving || vm.exiftoolExtensionsLoading || !vm.canConfigureExiftoolExtensions" style="width: 220px;">
								{{ vm.exiftoolExtensionsLoading ? vm.$avt('config:button_exiftool_extensions_loading', 'Loading ExifTool extensions...') : vm.$avt('config:button_exiftool_extensions_load', 'Load all ExifTool extensions') }}
							</v-button>
						</div>
					</label>
				</div>

				<div v-if="vm.exiftoolDownloadSourceUrl" class="config-card-desc">
					{{ vm.$avt('config:exiftool_download_source', 'Latest ExifTool package will be downloaded from: {url}', { url: vm.exiftoolDownloadSourceUrl }) }}
				</div>

				<div class="config-actions config-actions-right">
					<v-button @click="vm.installExiftool" :disabled="vm.externalLibrariesLoading || vm.externalLibrariesSaving || vm.exiftoolInstalling" style="width: 220px;">
						{{ vm.exiftoolInstalling ? vm.$avt('config:button_exiftool_installing', 'Installing ExifTool...') : vm.$avt('config:button_exiftool_install', 'Download and install ExifTool') }}
					</v-button>
					<v-button v-if="vm.hasBundledExiftool" @click="vm.removeExiftool" :disabled="vm.externalLibrariesLoading || vm.externalLibrariesSaving || vm.exiftoolInstalling || vm.exiftoolRemoving" style="width: 220px;">
						{{ vm.exiftoolRemoving ? vm.$avt('config:button_exiftool_removing', 'Removing ExifTool...') : vm.$avt('config:button_exiftool_remove', 'Remove ExifTool') }}
					</v-button>
				</div>
			</section>

			<section v-if="isPipPackagesConfigView" class="config-card">
				<div class="config-form-grid">
					<div class="config-card-desc">
						{{ vm.$avt('config:pip_packages_restart_hint', 'Enabled optional pip packages are installed during the next package start. Core packages remain required for startup; optional package installation failures are logged but do not block the package start.') }}
					</div>

					<div class="sm-kv-list">
						<div class="sm-kv-row">
							<div class="sm-kv-key">{{ vm.$avt('config:label_pip_package_status', 'InsightFace status') }}</div>
							<div class="sm-kv-value">
								{{ vm.insightFacePipPackageStatus.installed ? vm.$avt('status:installed', 'Installed') : vm.$avt('status:not_installed', 'Not installed') }}
							</div>
						</div>
						<div class="sm-kv-row">
							<div class="sm-kv-key">{{ vm.$avt('config:label_pip_package_enabled', 'Enabled in config') }}</div>
							<div class="sm-kv-value">
								{{ vm.insightFacePipPackageStatus.enabled ? vm.$avt('status:yes', 'Yes') : vm.$avt('status:no', 'No') }}
							</div>
						</div>
						<div class="sm-kv-row">
							<div class="sm-kv-key">{{ vm.$avt('config:label_pip_package_requirements', 'Requirements') }}</div>
							<div class="sm-kv-value">{{ vm.insightFacePipPackageStatus.requirements_file || '-' }}</div>
						</div>
						<div class="sm-kv-row">
							<div class="sm-kv-key">{{ vm.$avt('config:label_pip_wheelhouse_enabled', 'Wheelhouse download') }}</div>
							<div class="sm-kv-value">
								{{ vm.insightFacePipPackageStatus.wheelhouse_enabled ? vm.$avt('status:yes', 'Yes') : vm.$avt('status:no', 'No') }}
							</div>
						</div>
						<div v-if="vm.insightFacePipPackageStatus.wheelhouse_manifest_url" class="sm-kv-row">
							<div class="sm-kv-key">{{ vm.$avt('config:label_pip_wheelhouse_manifest_url', 'Wheelhouse manifest URL') }}</div>
							<div class="sm-kv-value">{{ vm.insightFacePipPackageStatus.wheelhouse_manifest_url }}</div>
						</div>
						<div v-if="vm.insightFacePipPackageStatus.wheelhouse_target" class="sm-kv-row">
							<div class="sm-kv-key">{{ vm.$avt('config:label_pip_wheelhouse_target', 'Wheelhouse target') }}</div>
							<div class="sm-kv-value">{{ vm.insightFacePipPackageStatus.wheelhouse_target }}</div>
						</div>
						<div class="sm-kv-row">
							<div class="sm-kv-key">{{ vm.$avt('config:label_pip_last_install_status', 'Last install status') }}</div>
							<div class="sm-kv-value">
								{{ vm.getPipPackageInstallStatusLabel(vm.insightFacePipPackageStatus.install_status) }}
							</div>
						</div>
						<div v-if="vm.insightFacePipPackageStatus.install_status && vm.insightFacePipPackageStatus.install_status.message" class="sm-kv-row">
							<div class="sm-kv-key">{{ vm.$avt('config:label_pip_last_install_message', 'Last install message') }}</div>
							<div class="sm-kv-value">{{ vm.insightFacePipPackageStatus.install_status.message }}</div>
						</div>
						<div v-if="vm.insightFaceModelStatus.root" class="sm-kv-row">
							<div class="sm-kv-key">{{ vm.$avt('config:label_insightface_model_root', 'InsightFace model root') }}</div>
							<div class="sm-kv-value">{{ vm.insightFaceModelStatus.root }}</div>
						</div>
						<div v-if="vm.insightFaceModelStatus.model_store" class="sm-kv-row">
							<div class="sm-kv-key">{{ vm.$avt('config:label_insightface_model_store', 'InsightFace model store') }}</div>
							<div class="sm-kv-value">{{ vm.insightFaceModelStatus.model_store }}</div>
						</div>
						<div v-if="vm.insightFaceActiveModelName" class="sm-kv-row">
							<div class="sm-kv-key">{{ vm.$avt('config:label_insightface_active_model', 'Active model') }}</div>
							<div class="sm-kv-value">{{ vm.insightFaceActiveModelName }}</div>
						</div>
						<template v-if="Array.isArray(vm.insightFacePipPackageStatus.modules)">
							<div
								v-for="moduleStatus in vm.insightFacePipPackageStatus.modules"
								:key="moduleStatus.package"
								class="sm-kv-row"
							>
								<div class="sm-kv-key">{{ moduleStatus.package }}</div>
								<div class="sm-kv-value">
									{{ vm.getPipPackageModuleStatusLabel(moduleStatus) }}
								</div>
							</div>
						</template>
						<div v-if="Array.isArray(vm.insightFacePipPackageStatus.conflicts) && vm.insightFacePipPackageStatus.conflicts.length" class="sm-kv-row">
							<div class="sm-kv-key">{{ vm.$avt('config:label_pip_conflicts', 'Package conflicts') }}</div>
							<div class="sm-kv-value">
								{{ vm.insightFacePipPackageStatus.conflicts.map((item) => `${item.package} ${item.version}`).join(', ') }}
							</div>
						</div>
						<template v-if="Array.isArray(vm.insightFaceModelStatus.models) && vm.insightFaceModelStatus.models.length">
							<div
								v-for="modelStatus in vm.insightFaceModelStatus.models"
								:key="`config-model-${modelStatus.name}`"
								class="sm-kv-row"
							>
								<div class="sm-kv-key">{{ vm.$avt('config:label_insightface_model', 'Model') }}: {{ modelStatus.name }}</div>
								<div class="sm-kv-value">{{ vm.getInsightFaceModelStatusLabel(modelStatus) }}</div>
							</div>
						</template>
					</div>

					<div class="config-actions config-actions-right">
						<v-button @click="vm.fetchPipPackagesStatus" :disabled="vm.pipPackagesStatusLoading" style="width: 220px;">
							{{ vm.pipPackagesStatusLoading ? vm.$avt('config:button_pip_status_loading', 'Checking pip packages...') : vm.$avt('config:button_pip_status_refresh', 'Refresh package status') }}
						</v-button>
					</div>

					<div class="config-card-desc">
						{{ vm.$avt('config:pip_wheelhouse_package_install_hint', 'Load the configured wheelhouse manifest, select one package from it, and install or reinstall that package. Reinstall downloads the wheelhouse assets again and does not use a local backup.') }}
					</div>

					<div class="config-actions config-actions-right">
						<v-button @click="vm.loadPipWheelhousePackages" :disabled="vm.pipWheelhousePackagesLoading || vm.pipWheelhousePackageInstalling || vm.pipWheelhousePackageReinstalling" style="width: 220px;">
							{{ vm.pipWheelhousePackagesLoading ? vm.$avt('config:button_pip_wheelhouse_loading', 'Loading wheelhouse...') : vm.$avt('config:button_pip_wheelhouse_load', 'Load wheelhouse packages') }}
						</v-button>
					</div>

					<label class="config-field">
						<span class="config-field-label">{{ vm.$avt('config:label_pip_wheelhouse_package', 'Wheelhouse package') }}</span>
						<select
							:value="vm.selectedPipWheelhousePackageName"
							class="config-input"
							:disabled="vm.externalLibrariesSaving || vm.pipWheelhousePackagesLoading || vm.pipWheelhousePackageInstalling || vm.pipWheelhousePackageReinstalling || !vm.pipWheelhousePackages.length"
							@change="vm.setSelectedPipWheelhousePackageName($event.target.value)"
						>
							<option value="">{{ vm.$avt('config:option_pip_wheelhouse_package_none', 'No package loaded') }}</option>
							<option
								v-for="packageInfo in vm.pipWheelhousePackages"
								:key="`pip-wheelhouse-package-${packageInfo.name}`"
								:value="packageInfo.name"
							>
								{{ packageInfo.name }}{{ packageInfo.installed_version ? ` (${vm.$avt('status:installed', 'Installed')}: ${packageInfo.installed_version})` : '' }}
							</option>
						</select>
					</label>

					<div v-if="vm.selectedPipWheelhousePackageStatus.file" class="sm-kv-list">
						<div class="sm-kv-row">
							<div class="sm-kv-key">{{ vm.$avt('config:label_pip_wheelhouse_file', 'Wheel file') }}</div>
							<div class="sm-kv-value">{{ vm.selectedPipWheelhousePackageStatus.file }}</div>
						</div>
						<div class="sm-kv-row">
							<div class="sm-kv-key">{{ vm.$avt('config:label_pip_wheelhouse_size', 'Wheel size') }}</div>
							<div class="sm-kv-value">{{ Number(vm.selectedPipWheelhousePackageStatus.size) || 0 }}</div>
						</div>
						<div class="sm-kv-row">
							<div class="sm-kv-key">{{ vm.$avt('config:label_pip_wheelhouse_installed_version', 'Installed version') }}</div>
							<div class="sm-kv-value">{{ vm.selectedPipWheelhousePackageStatus.installed_version || '-' }}</div>
						</div>
					</div>

					<div class="config-actions config-actions-right">
						<v-button
							@click="vm.installSelectedPipWheelhousePackage(false)"
							:disabled="!vm.selectedPipWheelhousePackageName || vm.pipWheelhousePackageInstalling || vm.pipWheelhousePackageReinstalling"
							style="width: 220px;"
						>
							{{ vm.pipWheelhousePackageInstalling ? vm.$avt('config:button_pip_package_installing', 'Installing package...') : vm.$avt('config:button_pip_package_install', 'Install selected package') }}
						</v-button>
						<v-button
							@click="vm.installSelectedPipWheelhousePackage(true)"
							:disabled="!vm.selectedPipWheelhousePackageName || vm.pipWheelhousePackageInstalling || vm.pipWheelhousePackageReinstalling"
							style="width: 220px;"
						>
							{{ vm.pipWheelhousePackageReinstalling ? vm.$avt('config:button_pip_package_reinstalling', 'Reinstalling package...') : vm.$avt('config:button_pip_package_reinstall', 'Reinstall selected package') }}
						</v-button>
					</div>

					<label class="config-checkbox">
						<input
							:checked="vm.externalLibrariesConfigModel.pip_packages.INSIGHTFACE.ENABLED"
							type="checkbox"
							:disabled="vm.externalLibrariesSaving"
							@change="vm.setExternalLibrariesPipPackageConfigValue('INSIGHTFACE', 'ENABLED', $event.target.checked)"
						/>
						<span>{{ vm.$avt('config:label_enable_insightface_package', 'Enable InsightFace component') }}</span>
					</label>

					<label class="config-checkbox">
						<input
							:checked="vm.externalLibrariesConfigModel.pip_packages.INSIGHTFACE.INSTALL_ON_START"
							type="checkbox"
							:disabled="vm.externalLibrariesSaving || !vm.externalLibrariesConfigModel.pip_packages.INSIGHTFACE.ENABLED"
							@change="vm.setExternalLibrariesPipPackageConfigValue('INSIGHTFACE', 'INSTALL_ON_START', $event.target.checked)"
						/>
						<span>{{ vm.$avt('config:label_pip_install_on_start', 'Install or update during package start') }}</span>
					</label>

					<label class="config-field">
						<span class="config-field-label">{{ vm.$avt('config:label_pip_wheelhouse_manifest_url', 'Wheelhouse manifest URL') }}</span>
						<input
							:value="vm.externalLibrariesConfigModel.pip_packages.INSIGHTFACE.WHEELHOUSE_MANIFEST_URL"
							type="text"
							class="config-input"
							:disabled="vm.externalLibrariesSaving || !vm.externalLibrariesConfigModel.pip_packages.INSIGHTFACE.ENABLED"
							@input="vm.setExternalLibrariesPipPackageConfigValue('INSIGHTFACE', 'WHEELHOUSE_MANIFEST_URL', $event.target.value)"
						/>
						<span class="config-card-desc">
							{{ vm.$avt('config:hint_pip_wheelhouse_manifest_url', 'Points to the wheelhouse-manifest.json of a compatible release. The manifest is the lock for the wheelhouse install: all wheel files listed there are downloaded, verified via SHA256 and then installed locally without source builds.') }}
						</span>
					</label>

					<label class="config-field">
						<span class="config-field-label">{{ vm.$avt('config:label_pip_wheelhouse_target', 'Wheelhouse target') }}</span>
						<input
							:value="vm.externalLibrariesConfigModel.pip_packages.INSIGHTFACE.WHEELHOUSE_TARGET"
							type="text"
							class="config-input"
							:disabled="vm.externalLibrariesSaving || !vm.externalLibrariesConfigModel.pip_packages.INSIGHTFACE.ENABLED"
							@input="vm.setExternalLibrariesPipPackageConfigValue('INSIGHTFACE', 'WHEELHOUSE_TARGET', $event.target.value)"
						/>
						<span class="config-card-desc">
							{{ vm.$avt('config:hint_pip_wheelhouse_target', 'Must match the manifest target exactly, for example dsm7-x86_64-python38.') }}
						</span>
					</label>

					<label class="config-field">
						<span class="config-field-label">{{ vm.$avt('config:label_insightface_selected_model', 'InsightFace model for face search') }}</span>
						<input
							:value="vm.externalLibrariesConfigModel.pip_packages.INSIGHTFACE.MODEL_NAME"
							type="text"
							class="config-input"
							list="insightface-model-options"
							:placeholder="vm.$avt('config:placeholder_insightface_model_default', 'InsightFace default')"
							:disabled="vm.externalLibrariesSaving || !vm.externalLibrariesConfigModel.pip_packages.INSIGHTFACE.ENABLED"
							@input="vm.setExternalLibrariesPipPackageConfigValue('INSIGHTFACE', 'MODEL_NAME', $event.target.value)"
						/>
						<datalist id="insightface-model-options">
							<option
								v-for="modelName in vm.insightFaceInstalledModelNames"
								:key="`insightface-model-option-${modelName}`"
								:value="modelName"
							/>
						</datalist>
						<span class="config-card-desc">
							{{ vm.$avt('config:hint_insightface_selected_model', 'Leave empty to use the InsightFace package default, select an installed model, or enter a model name that InsightFace can resolve.') }}
						</span>
					</label>

					<div class="config-card-desc">
						{{ vm.$avt('config:pip_packages_insightface_license_hint', 'InsightFace code and model files have separate licensing considerations. No models are shipped or downloaded automatically by AV ImgData.') }}
					</div>

					<div class="config-card-desc">
						{{ vm.$avt('config:insightface_model_management_hint', 'Model packages are read from the InsightFace model store. Upload a ZIP package to install a local model, or configure a model name that the installed InsightFace package can resolve itself.') }}
					</div>

					<div class="sm-kv-list">
						<div class="sm-kv-row">
							<div class="sm-kv-key">{{ vm.$avt('config:label_insightface_model_root', 'InsightFace model root') }}</div>
							<div class="sm-kv-value">{{ vm.insightFaceModelStatus.root || '-' }}</div>
						</div>
						<div class="sm-kv-row">
							<div class="sm-kv-key">{{ vm.$avt('config:label_insightface_model_store', 'InsightFace model store') }}</div>
							<div class="sm-kv-value">{{ vm.insightFaceModelStatus.model_store || '-' }}</div>
						</div>
					</div>

					<template v-if="Array.isArray(vm.insightFaceModelStatus.models) && vm.insightFaceModelStatus.models.length">
						<div
							v-for="modelStatus in vm.insightFaceModelStatus.models"
							:key="`manage-model-${modelStatus.name}`"
							class="sm-kv-row sm-kv-row-spread"
						>
							<div class="sm-kv-key">{{ vm.$avt('config:label_insightface_model', 'Model') }}: {{ modelStatus.name }}</div>
							<div class="sm-kv-value">
								{{ vm.getInsightFaceModelStatusLabel(modelStatus) }}
								<v-button
									v-if="modelStatus.installed"
									@click="vm.deleteInsightFaceModel(modelStatus.name)"
									:disabled="vm.externalLibrariesSaving || vm.insightFaceModelDeleting === modelStatus.name"
									style="width: 140px; margin-left: 12px;"
								>
									{{ vm.insightFaceModelDeleting === modelStatus.name ? vm.$avt('config:button_insightface_model_deleting', 'Deleting model...') : vm.$avt('config:button_insightface_model_delete', 'Delete model') }}
								</v-button>
							</div>
						</div>
					</template>
				</div>
			</section>
		</div>
	</section>
</template>

<script>
export default {
	name: 'ExternalLibrariesView',
	props: {
		mode: {
			type: String,
			default: 'info',
			validator: (value) => ['info', 'config', 'pip_packages'].includes(value),
		},
		vm: {
			type: Object,
			required: true,
		},
	},
	computed: {
		isExternalLibrariesInfoView() {
			return this.mode === 'info';
		},
		isExiftoolConfigView() {
			return this.mode === 'config';
		},
		isPipPackagesConfigView() {
			return this.mode === 'pip_packages';
		},
		isEditableConfigView() {
			return this.isExiftoolConfigView || this.isPipPackagesConfigView;
		},
		panelTitle() {
			if (this.isExiftoolConfigView) {
				return this.vm.$avt('nav:exiftool', 'ExifTool');
			}
			if (this.isPipPackagesConfigView) {
				return this.vm.$avt('nav:pip_packages', 'pip packages');
			}
			return this.vm.$avt('nav:external_libraries', 'External libraries');
		},
		panelDescription() {
			if (this.isPipPackagesConfigView) {
				return this.vm.$avt('config:section_pip_packages_desc', 'Configure optional Python packages installed into the package venv after an explicit restart.');
			}
			return this.vm.$avt('config:section_exiftool_desc', 'Settings for optional ExifTool usage when reading embedded XMP metadata.');
		},
	},
};
</script>
