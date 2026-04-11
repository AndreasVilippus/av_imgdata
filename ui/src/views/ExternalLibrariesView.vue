<template>
	<section class="panel">
		<div class="panel-head">
			<div class="sm-section-title">{{ panelTitle }}</div>
		</div>

		<div v-if="isExiftoolConfigView" class="config-actions config-actions-right">
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

			<section v-if="isExiftoolConfigView" class="config-card">
				<div class="sm-section-title">{{ vm.$t('config:section_exiftool', 'ExifTool') }}</div>
				<div class="config-card-desc">{{ vm.$t('config:section_exiftool_desc', 'Settings for optional ExifTool usage when reading embedded XMP metadata.') }}</div>

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
						<label
							class="config-checkbox"
							:title="vm.$t('config:hint_image_extensions_native_only', 'If enabled, the native image extension list is only used by native readers. ExifTool uses its own extension list instead.')"
						>
							<input
								:checked="vm.externalLibrariesConfigModel.files.IMAGE_EXTENSIONS_NATIVE_ONLY"
								type="checkbox"
								:disabled="vm.externalLibrariesSaving"
								@change="vm.setExternalLibrariesFileConfigValue('IMAGE_EXTENSIONS_NATIVE_ONLY', $event.target.checked)"
							/>
							<span>{{ vm.$t('config:label_image_extensions_native_only', 'Use native extension list only for native readers') }}</span>
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
			validator: (value) => ['info', 'config'].includes(value),
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
		panelTitle() {
			return this.isExiftoolConfigView
				? this.vm.$t('nav:exiftool', 'ExifTool')
				: this.vm.$t('nav:external_libraries', 'External libraries');
		},
	},
};
</script>
