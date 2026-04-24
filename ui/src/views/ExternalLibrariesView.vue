<template>
	<section class="panel">
		<div class="panel-head">
			<div class="sm-section-title">{{ panelTitle }}</div>
			<p v-if="panelDescription">{{ panelDescription }}</p>
		</div>

		<div v-if="isEditableConfigView" class="config-actions config-actions-right">
			<v-button @click="vm.loadExternalLibrariesConfig" :disabled="vm.externalLibrariesLoading || vm.externalLibrariesSaving" style="width: 160px;">
				{{ vm.$t('config:button_reload', 'Reload') }}
			</v-button>
			<v-button @click="vm.applyExternalLibrariesDefaults" :disabled="vm.externalLibrariesLoading || vm.externalLibrariesSaving" style="width: 160px;">
				{{ vm.$t('config:button_defaults', 'Defaults') }}
			</v-button>
			<v-button @click="vm.saveExternalLibrariesConfig" :disabled="vm.externalLibrariesLoading || vm.externalLibrariesSaving" style="width: 160px;">
				{{ vm.$t('config:button_save', 'Save') }}
			</v-button>
		</div>

		<div v-if="vm.externalLibrariesMessage" class="config-message">{{ vm.externalLibrariesMessage }}</div>

		<div v-if="vm.externalLibrariesLoading" class="config-loading">
			<span class="sm-loader"></span>
			{{ vm.$t('config:loading', 'Loading configuration...') }}
		</div>

		<div v-else class="config-layout">
			<section v-if="isExternalLibrariesInfoView" class="config-card">
				<div class="sm-section-title">{{ vm.$t('status:exiftool_title', 'ExifTool') }}</div>
				<div class="sm-kv-list">
					<div class="sm-kv-row">
						<div class="sm-kv-key">{{ vm.$t('status:exiftool_found', 'Found') }}</div>
						<div class="sm-kv-value">{{ vm.hasLocalExiftool ? vm.$t('status:yes', 'Yes') : vm.$t('status:no', 'No') }}</div>
					</div>
					<div class="sm-kv-row">
						<div class="sm-kv-key">{{ vm.$t('status:exiftool_configured_path', 'Configured path') }}</div>
						<div class="sm-kv-value">{{ vm.exiftoolStatus.configured_path || vm.$t('status:not_available', 'Not available') }}</div>
					</div>
					<template v-if="vm.hasLocalExiftool">
						<div class="sm-kv-row">
							<div class="sm-kv-key">{{ vm.$t('status:exiftool_local_version', 'Local version') }}</div>
							<div class="sm-kv-value">{{ vm.exiftoolStatus.local && vm.exiftoolStatus.local.version || vm.$t('status:not_available', 'Not available') }}</div>
						</div>
						<div class="sm-kv-row">
							<div class="sm-kv-key">{{ vm.$t('status:exiftool_latest_version', 'Latest official version') }}</div>
							<div class="sm-kv-value">{{ vm.exiftoolStatus.online && vm.exiftoolStatus.online.latest_version || vm.$t('status:not_available', 'Not available') }}</div>
						</div>
						<div class="sm-kv-row">
							<div class="sm-kv-key">{{ vm.$t('status:exiftool_update_available', 'Update available') }}</div>
							<div class="sm-kv-value">{{ vm.exiftoolStatus.update_available ? vm.$t('status:yes', 'Yes') : vm.$t('status:no', 'No') }}</div>
						</div>
						<div class="sm-kv-row">
							<div class="sm-kv-key">{{ vm.$t('status:exiftool_resolved_path', 'Resolved path') }}</div>
							<div class="sm-kv-value">{{ vm.exiftoolStatus.local && vm.exiftoolStatus.local.resolved_path || vm.$t('status:not_available', 'Not available') }}</div>
						</div>
					</template>
				</div>
			</section>

			<section v-if="isExternalLibrariesInfoView" class="config-card">
				<div class="sm-section-title">{{ vm.$t('nav:pip_packages', 'pip packages') }}</div>
				<div class="sm-kv-list">
					<div class="sm-kv-row">
						<div class="sm-kv-key">{{ vm.$t('config:label_pip_package_status', 'InsightFace status') }}</div>
						<div class="sm-kv-value">
							{{ vm.insightFacePipPackageStatus.installed ? vm.$t('status:installed', 'Installed') : vm.$t('status:not_installed', 'Not installed') }}
						</div>
					</div>
					<div class="sm-kv-row">
						<div class="sm-kv-key">{{ vm.$t('config:label_pip_package_enabled', 'Enabled in config') }}</div>
						<div class="sm-kv-value">
							{{ vm.insightFacePipPackageStatus.enabled ? vm.$t('status:yes', 'Yes') : vm.$t('status:no', 'No') }}
						</div>
					</div>
					<div class="sm-kv-row">
						<div class="sm-kv-key">{{ vm.$t('config:label_pip_last_install_status', 'Last install status') }}</div>
						<div class="sm-kv-value">
							{{ vm.getPipPackageInstallStatusLabel(vm.insightFacePipPackageStatus.install_status) }}
						</div>
					</div>
					<div v-if="vm.insightFacePipPackageStatus.install_status && vm.insightFacePipPackageStatus.install_status.message" class="sm-kv-row">
						<div class="sm-kv-key">{{ vm.$t('config:label_pip_last_install_message', 'Last install message') }}</div>
						<div class="sm-kv-value">{{ vm.insightFacePipPackageStatus.install_status.message }}</div>
					</div>
					<div v-if="vm.insightFaceModelStatus.root" class="sm-kv-row">
						<div class="sm-kv-key">{{ vm.$t('config:label_insightface_model_root', 'InsightFace model root') }}</div>
						<div class="sm-kv-value">{{ vm.insightFaceModelStatus.root }}</div>
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
						<div class="sm-kv-key">{{ vm.$t('config:label_pip_conflicts', 'Package conflicts') }}</div>
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
							<div class="sm-kv-key">{{ vm.$t('config:label_insightface_model', 'Model') }}: {{ modelStatus.name }}</div>
							<div class="sm-kv-value">{{ vm.getInsightFaceModelStatusLabel(modelStatus) }}</div>
						</div>
					</template>
				</div>
			</section>

			<section v-if="isExiftoolConfigView" class="config-card">
				<div class="config-form-grid">
					<label v-if="vm.hasUsableExiftool" class="config-checkbox">
						<input
							:checked="vm.externalLibrariesConfigModel.files.USE_EXIFTOOL"
							type="checkbox"
							:disabled="vm.externalLibrariesSaving"
							@change="vm.setExternalLibrariesFileConfigValue('USE_EXIFTOOL', $event.target.checked)"
						/>
						<span>{{ vm.$t('config:label_use_exiftool', 'Use ExifTool for embedded XMP') }}</span>
					</label>

					<label class="config-checkbox">
						<input
							:checked="vm.externalLibrariesConfigModel.files.CHECK_EXIFTOOL_UPDATES"
							type="checkbox"
							:disabled="vm.externalLibrariesSaving"
							@change="vm.setExternalLibrariesFileConfigValue('CHECK_EXIFTOOL_UPDATES', $event.target.checked)"
						/>
						<span>{{ vm.$t('config:label_check_exiftool_updates', 'Check for newer ExifTool versions') }}</span>
					</label>

					<template v-if="vm.externalLibrariesConfigModel.files.USE_EXIFTOOL">
						<label class="config-checkbox">
							<input
								:checked="vm.externalLibrariesConfigModel.files.USE_MANUAL_PATHEXIFTOOL"
								type="checkbox"
								:disabled="vm.externalLibrariesSaving"
								@change="vm.setExternalLibrariesFileConfigValue('USE_MANUAL_PATHEXIFTOOL', $event.target.checked)"
							/>
							<span>{{ vm.$t('config:label_use_manual_exiftool_path', 'Use manual path to ExifTool') }}</span>
						</label>

						<label
							v-if="vm.externalLibrariesConfigModel.files.USE_MANUAL_PATHEXIFTOOL"
							class="config-field"
						>
							<span class="config-field-label">{{ vm.$t('config:label_manual_exiftool_path', 'Path to ExifTool') }}</span>
							<input
								:value="vm.externalLibrariesConfigModel.files.MANUAL_PATHEXIFTOOL"
								type="text"
								class="config-input"
								:disabled="vm.externalLibrariesSaving"
								:placeholder="vm.$t('config:placeholder_manual_exiftool_path', '/usr/local/bin/exiftool')"
								@input="vm.setExternalLibrariesFileConfigValue('MANUAL_PATHEXIFTOOL', $event.target.value)"
							/>
							<span class="config-card-desc">
								{{ vm.$t('config:hint_manual_exiftool_path', 'When enabled, this path is used instead of the bundled ExifTool path and is not changed by install or remove actions.') }}
							</span>
						</label>

						<label
							class="config-checkbox"
							:title="vm.$t('config:hint_image_extensions_native_only', 'If enabled, the file extension list for metadata scanning is only used by native readers. ExifTool uses its own extension list instead.')"
						>
							<input
								:checked="vm.externalLibrariesConfigModel.files.IMAGE_EXTENSIONS_NATIVE_ONLY"
								type="checkbox"
								:disabled="vm.externalLibrariesSaving"
								@change="vm.setExternalLibrariesFileConfigValue('IMAGE_EXTENSIONS_NATIVE_ONLY', $event.target.checked)"
							/>
							<span>{{ vm.$t('config:label_image_extensions_native_only', 'Use metadata scan file extensions only for native readers') }}</span>
						</label>

						<label
							class="config-checkbox"
							:title="vm.$t('config:hint_use_exiftool_for_sidecars', 'The native sidecar path usually works well and is faster. Only enable this when sidecar reading causes problems.')"
						>
							<input
								:checked="vm.externalLibrariesConfigModel.files.USE_EXIFTOOL_FOR_SIDECARS"
								type="checkbox"
								:disabled="vm.externalLibrariesSaving"
								@change="vm.setExternalLibrariesFileConfigValue('USE_EXIFTOOL_FOR_SIDECARS', $event.target.checked)"
							/>
							<span>{{ vm.$t('config:label_use_exiftool_for_sidecars', 'Use ExifTool for XMP sidecars') }}</span>
						</label>

						<label
							class="config-checkbox"
							:title="vm.$t('config:hint_prefer_exiftool_for_context', 'Native context readers are usually faster. Enable this only if ExifTool should be preferred for dimensions and orientation, otherwise ExifTool is only used as a fallback.')"
						>
							<input
								:checked="vm.externalLibrariesConfigModel.files.PREFER_EXIFTOOL_FOR_CONTEXT"
								type="checkbox"
								:disabled="vm.externalLibrariesSaving"
								@change="vm.setExternalLibrariesFileConfigValue('PREFER_EXIFTOOL_FOR_CONTEXT', $event.target.checked)"
							/>
							<span>{{ vm.$t('config:label_prefer_exiftool_for_context', 'Prefer ExifTool for metadata context') }}</span>
						</label>

						<label class="config-field">
							<span class="config-field-label">{{ vm.$t('config:label_exiftool_image_extensions', 'ExifTool file extensions for metadata scan') }}</span>
							<textarea
								:value="vm.exiftoolImageExtensionsInput"
								class="config-textarea"
								:disabled="vm.externalLibrariesSaving || vm.exiftoolExtensionsLoading"
								:placeholder="vm.$t('config:placeholder_exiftool_image_extensions', 'Leave empty to use all readable extensions reported by ExifTool.')"
								@input="vm.setExiftoolImageExtensionsInput($event.target.value)"
							></textarea>
							<span class="config-card-desc">
								{{ vm.$t('config:hint_exiftool_image_extensions', 'When the field is empty, all readable ExifTool extensions are queried automatically.') }}
							</span>
							<div class="config-inline-actions">
								<v-button
									@click="vm.loadExiftoolExtensions"
									:disabled="vm.externalLibrariesSaving || vm.exiftoolExtensionsLoading"
									style="width: 220px;"
								>
									{{ vm.exiftoolExtensionsLoading ? vm.$t('config:button_exiftool_extensions_loading', 'Loading ExifTool extensions...') : vm.$t('config:button_exiftool_extensions_load', 'Load all ExifTool extensions') }}
								</v-button>
							</div>
						</label>
					</template>
				</div>

				<div v-if="vm.exiftoolDownloadSourceUrl" class="config-card-desc">
					{{ vm.$t('config:exiftool_download_source', 'Latest ExifTool package will be downloaded from: {url}', { url: vm.exiftoolDownloadSourceUrl }) }}
				</div>

				<div class="config-actions config-actions-right">
					<v-button @click="vm.installExiftool" :disabled="vm.externalLibrariesLoading || vm.externalLibrariesSaving || vm.exiftoolInstalling" style="width: 220px;">
						{{ vm.exiftoolInstalling ? vm.$t('config:button_exiftool_installing', 'Installing ExifTool...') : vm.$t('config:button_exiftool_install', 'Download and install ExifTool') }}
					</v-button>
					<v-button
						v-if="vm.hasBundledExiftool"
						@click="vm.removeExiftool"
						:disabled="vm.externalLibrariesLoading || vm.externalLibrariesSaving || vm.exiftoolInstalling || vm.exiftoolRemoving"
						style="width: 220px;"
					>
						{{ vm.exiftoolRemoving ? vm.$t('config:button_exiftool_removing', 'Removing ExifTool...') : vm.$t('config:button_exiftool_remove', 'Remove ExifTool') }}
					</v-button>
				</div>
			</section>

			<section v-if="isPipPackagesConfigView" class="config-card">
				<div class="config-form-grid">
					<div class="config-card-desc">
						{{ vm.$t('config:pip_packages_restart_hint', 'Enabled optional pip packages are installed during the next package start. Core packages remain required for startup; optional package installation failures are logged but do not block the package start.') }}
					</div>

					<div class="sm-kv-list">
						<div class="sm-kv-row">
							<div class="sm-kv-key">{{ vm.$t('config:label_pip_package_status', 'InsightFace status') }}</div>
							<div class="sm-kv-value">
								{{ vm.insightFacePipPackageStatus.installed ? vm.$t('status:installed', 'Installed') : vm.$t('status:not_installed', 'Not installed') }}
							</div>
						</div>
						<div class="sm-kv-row">
							<div class="sm-kv-key">{{ vm.$t('config:label_pip_package_enabled', 'Enabled in config') }}</div>
							<div class="sm-kv-value">
								{{ vm.insightFacePipPackageStatus.enabled ? vm.$t('status:yes', 'Yes') : vm.$t('status:no', 'No') }}
							</div>
						</div>
						<div class="sm-kv-row">
							<div class="sm-kv-key">{{ vm.$t('config:label_pip_package_requirements', 'Requirements') }}</div>
							<div class="sm-kv-value">{{ vm.insightFacePipPackageStatus.requirements_file || '-' }}</div>
						</div>
						<div class="sm-kv-row">
							<div class="sm-kv-key">{{ vm.$t('config:label_pip_wheelhouse_enabled', 'Wheelhouse download') }}</div>
							<div class="sm-kv-value">
								{{ vm.insightFacePipPackageStatus.wheelhouse_enabled ? vm.$t('status:yes', 'Yes') : vm.$t('status:no', 'No') }}
							</div>
						</div>
						<div v-if="vm.insightFacePipPackageStatus.wheelhouse_manifest_url" class="sm-kv-row">
							<div class="sm-kv-key">{{ vm.$t('config:label_pip_wheelhouse_manifest_url', 'Wheelhouse manifest URL') }}</div>
							<div class="sm-kv-value">{{ vm.insightFacePipPackageStatus.wheelhouse_manifest_url }}</div>
						</div>
						<div v-if="vm.insightFacePipPackageStatus.wheelhouse_target" class="sm-kv-row">
							<div class="sm-kv-key">{{ vm.$t('config:label_pip_wheelhouse_target', 'Wheelhouse target') }}</div>
							<div class="sm-kv-value">{{ vm.insightFacePipPackageStatus.wheelhouse_target }}</div>
						</div>
						<div class="sm-kv-row">
							<div class="sm-kv-key">{{ vm.$t('config:label_pip_last_install_status', 'Last install status') }}</div>
							<div class="sm-kv-value">
								{{ vm.getPipPackageInstallStatusLabel(vm.insightFacePipPackageStatus.install_status) }}
							</div>
						</div>
						<div v-if="vm.insightFacePipPackageStatus.install_status && vm.insightFacePipPackageStatus.install_status.message" class="sm-kv-row">
							<div class="sm-kv-key">{{ vm.$t('config:label_pip_last_install_message', 'Last install message') }}</div>
							<div class="sm-kv-value">{{ vm.insightFacePipPackageStatus.install_status.message }}</div>
						</div>
						<div v-if="vm.insightFaceModelStatus.root" class="sm-kv-row">
							<div class="sm-kv-key">{{ vm.$t('config:label_insightface_model_root', 'InsightFace model root') }}</div>
							<div class="sm-kv-value">{{ vm.insightFaceModelStatus.root }}</div>
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
							<div class="sm-kv-key">{{ vm.$t('config:label_pip_conflicts', 'Package conflicts') }}</div>
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
								<div class="sm-kv-key">{{ vm.$t('config:label_insightface_model', 'Model') }}: {{ modelStatus.name }}</div>
								<div class="sm-kv-value">{{ vm.getInsightFaceModelStatusLabel(modelStatus) }}</div>
							</div>
						</template>
					</div>

					<div class="config-actions config-actions-right">
						<v-button @click="vm.fetchPipPackagesStatus" :disabled="vm.pipPackagesStatusLoading" style="width: 220px;">
							{{ vm.pipPackagesStatusLoading ? vm.$t('config:button_pip_status_loading', 'Checking pip packages...') : vm.$t('config:button_pip_status_refresh', 'Refresh package status') }}
						</v-button>
					</div>

					<label class="config-checkbox">
						<input
							:checked="vm.externalLibrariesConfigModel.pip_packages.INSIGHTFACE.ENABLED"
							type="checkbox"
							:disabled="vm.externalLibrariesSaving"
							@change="vm.setExternalLibrariesPipPackageConfigValue('INSIGHTFACE', 'ENABLED', $event.target.checked)"
						/>
						<span>{{ vm.$t('config:label_enable_insightface_package', 'Install InsightFace package on package start') }}</span>
					</label>

					<label class="config-checkbox">
						<input
							:checked="vm.externalLibrariesConfigModel.pip_packages.INSIGHTFACE.INSTALL_ON_START"
							type="checkbox"
							:disabled="vm.externalLibrariesSaving || !vm.externalLibrariesConfigModel.pip_packages.INSIGHTFACE.ENABLED"
							@change="vm.setExternalLibrariesPipPackageConfigValue('INSIGHTFACE', 'INSTALL_ON_START', $event.target.checked)"
						/>
						<span>{{ vm.$t('config:label_pip_install_on_start', 'Install or update during package start') }}</span>
					</label>

					<label class="config-field">
						<span class="config-field-label">{{ vm.$t('config:label_pip_wheelhouse_manifest_url', 'Wheelhouse manifest URL') }}</span>
						<input
							:value="vm.externalLibrariesConfigModel.pip_packages.INSIGHTFACE.WHEELHOUSE_MANIFEST_URL"
							type="text"
							class="config-input"
							:disabled="vm.externalLibrariesSaving || !vm.externalLibrariesConfigModel.pip_packages.INSIGHTFACE.ENABLED"
							@input="vm.setExternalLibrariesPipPackageConfigValue('INSIGHTFACE', 'WHEELHOUSE_MANIFEST_URL', $event.target.value)"
						/>
						<span class="config-card-desc">
							{{ vm.$t('config:hint_pip_wheelhouse_manifest_url', 'Points to the wheelhouse-manifest.json of a compatible release. The manifest is the lock for the wheelhouse install: all wheel files listed there are downloaded, verified via SHA256 and then installed locally without source builds.') }}
						</span>
					</label>

					<label class="config-field">
						<span class="config-field-label">{{ vm.$t('config:label_pip_wheelhouse_target', 'Wheelhouse target') }}</span>
						<input
							:value="vm.externalLibrariesConfigModel.pip_packages.INSIGHTFACE.WHEELHOUSE_TARGET"
							type="text"
							class="config-input"
							:disabled="vm.externalLibrariesSaving || !vm.externalLibrariesConfigModel.pip_packages.INSIGHTFACE.ENABLED"
							@input="vm.setExternalLibrariesPipPackageConfigValue('INSIGHTFACE', 'WHEELHOUSE_TARGET', $event.target.value)"
						/>
						<span class="config-card-desc">
							{{ vm.$t('config:hint_pip_wheelhouse_target', 'Must match the manifest target exactly, for example dsm7-x86_64-python38.') }}
						</span>
					</label>

					<div class="config-card-desc">
						{{ vm.$t('config:pip_packages_insightface_license_hint', 'InsightFace code and model files have separate licensing considerations. No models are shipped or downloaded automatically by AV ImgData.') }}
					</div>
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
				return this.vm.$t('nav:exiftool', 'ExifTool');
			}
			if (this.isPipPackagesConfigView) {
				return this.vm.$t('nav:pip_packages', 'pip packages');
			}
			return this.vm.$t('nav:external_libraries', 'External libraries');
		},
		panelDescription() {
			if (this.isPipPackagesConfigView) {
				return this.vm.$t('config:section_pip_packages_desc', 'Configure optional Python packages installed into the package venv after an explicit restart.');
			}
			return this.vm.$t('config:section_exiftool_desc', 'Settings for optional ExifTool usage when reading embedded XMP metadata.');
		},
	},
};
</script>
