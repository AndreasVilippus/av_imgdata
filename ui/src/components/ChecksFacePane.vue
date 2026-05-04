<template>
	<div class="face-match-col">
		<h2>{{ title }}</h2>
		<div v-if="vm.isChecksDuplicateFaces(item)" class="checks-face-name checks-face-name-input-wrap">
			<label class="checks-face-name-field">
				<input
					v-model.trim="assignment.name"
					type="text"
					class="face-match-result-name-input"
					:placeholder="vm.$avt('checks:name_placeholder', 'Name of the person')"
					@input="vm.handleChecksDuplicateNameInput(side)"
					@focus="vm.handleChecksDuplicateNameFocus(side)"
				/>
				<div v-if="assignment.showSuggestions && (assignment.suggestLoading || assignment.suggestions.length)" class="face-match-suggest-list">
					<div v-if="assignment.suggestLoading" class="face-match-suggest-loading">
						<span class="sm-loader"></span>
						{{ vm.$avt('face_match:suggest_loading', 'Loading suggestions...') }}
					</div>
					<button
						v-for="person in assignment.suggestions"
						:key="`checks-${side}-person-suggest-${person.id}`"
						type="button"
						class="face-match-suggest-item"
						@click="vm.selectChecksDuplicateSuggestion(side, person)"
					>
						<img :src="vm.getFaceMatchPersonPreviewUrl(person)" alt="" class="face-match-suggest-thumb" />
						<span class="face-match-suggest-text">
							<span class="face-match-suggest-name">{{ person.name || vm.$avt('face_match:unknown_name', '(unnamed)') }}</span>
							<span class="face-match-suggest-meta">{{ vm.$avt('face_match:suggest_person_id', 'Photos Person-ID: {id}', { id: person.id }) }}</span>
						</span>
					</button>
				</div>
			</label>
		</div>
		<div v-else-if="vm.showChecksFaceName(item)" class="checks-face-name">
			{{ vm.getChecksDisplayName(displayName) }}
		</div>
		<div v-if="vm.getChecksImageUrl(item)" class="face-match-thumbnail-wrap">
			<button
				v-if="!vm.isChecksNameConflict(item) && vm.canDeleteChecksFace(item, targetFace)"
				type="button"
				class="face-match-icon-button"
				:class="deleteButtonClass"
				:title="vm.$avt('checks:tooltip_delete_face', 'Delete face from metadata')"
				:aria-label="vm.$avt('checks:tooltip_delete_face', 'Delete face from metadata')"
				:disabled="vm.checksLoading || vm.checksActionLocked"
				@click.prevent="vm.deleteChecksMetadataFace(targetFace)"
			>
				<span class="face-match-icon-stack">
					<img :src="vm.getChecksDeleteFaceBaseIconUrl()" alt="" class="face-match-icon-image" />
					<img :src="vm.getChecksDeleteFaceOverlayIconUrl()" alt="" class="face-match-icon-overlay" />
				</span>
			</button>
			<button
				v-if="vm.isChecksDuplicateFaces(item)"
				type="button"
				class="face-match-icon-button"
				:class="syncButtonClass"
				:title="vm.$avt('checks:tooltip_assign_known_person', 'Assign selected known person')"
				:aria-label="vm.$avt('checks:tooltip_assign_known_person', 'Assign selected known person')"
				:disabled="!vm.canAssignChecksFaceToPerson(item, side)"
				@click.prevent="vm.assignChecksFaceToPerson(side)"
			>
				<span class="face-match-icon-stack">
					<img :src="vm.getChecksSyncFaceBaseIconUrl()" alt="" class="face-match-icon-image" />
					<img :src="vm.getChecksSyncFaceOverlayIconUrl()" alt="" class="face-match-icon-overlay" />
				</span>
			</button>
			<button
				v-if="vm.isChecksPositionDeviation(item) && vm.canReplaceChecksFacePosition(item, targetFace, positionSourceFace)"
				type="button"
				class="face-match-icon-button"
				:class="positionButtonClass"
				:title="positionTooltip"
				:aria-label="positionTooltip"
				:disabled="vm.checksLoading"
				@click.prevent="vm.replaceChecksMetadataFacePosition(targetFace, positionSourceFace)"
			>
				<img v-if="positionIconUrl" :src="positionIconUrl" alt="" class="face-match-icon-image" />
				<span v-else class="face-match-icon-fallback">{{ positionFallback }}</span>
			</button>
			<div class="face-match-preview">
				<img
					:src="vm.getChecksImageUrl(item)"
					:alt="vm.$avt('checks:image_alt', 'Check preview')"
					class="face-match-thumbnail"
				/>
				<div
					v-for="(maskStyle, index) in vm.getFaceMatchMaskStyles(face)"
					:key="`checks-${side}-mask-${index}`"
					class="face-match-mask"
					:style="maskStyle"
				></div>
				<div
					v-for="(referenceFace, index) in referenceFaces"
					:key="`checks-${side}-reference-${index}`"
					class="face-match-bbox"
					:style="vm.getChecksReferenceBoxStyle(referenceFace)"
				></div>
				<div
					v-for="(alertFace, index) in alertFaces"
					:key="`checks-${side}-alert-${index}`"
					class="face-match-bbox"
					:style="vm.getChecksAlertBoxStyle(alertFace, face)"
				></div>
				<div
					v-if="vm.getFaceMatchBoxStyle(face)"
					class="face-match-bbox"
					:style="vm.getChecksAlertBoxStyle(face, face, faceState)"
				></div>
			</div>
		</div>
		<div v-else class="face-match-empty">{{ vm.$avt('checks:empty_image', 'No preview available.') }}</div>
	</div>
</template>

<script>
export default {
	name: 'ChecksFacePane',
	props: {
		vm: {
			type: Object,
			required: true,
		},
		item: {
			type: Object,
			required: true,
		},
		side: {
			type: String,
			required: true,
			validator(value) {
				return ['left', 'right'].includes(value);
			},
		},
	},
	computed: {
		isLeft() {
			return this.side === 'left';
		},
		assignment() {
			return this.vm.checksDuplicateAssignments[this.side];
		},
		title() {
			return this.isLeft
				? this.vm.getChecksLeftTitle(this.item)
				: this.vm.getChecksRightTitle(this.item);
		},
		displayName() {
			return this.isLeft ? this.item.left_name : this.item.right_name;
		},
		face() {
			return this.isLeft ? this.item.left_face : this.item.right_face;
		},
		targetFace() {
			return this.isLeft ? this.item.left_face_target : this.item.right_face_target;
		},
		positionSourceFace() {
			return this.isLeft ? this.item.right_face : this.item.left_face;
		},
		referenceFaces() {
			return this.isLeft
				? (this.item.left_reference_faces || [])
				: (this.item.right_reference_faces || []);
		},
		alertFaces() {
			return this.isLeft
				? (this.item.left_alert_faces || [])
				: (this.item.right_alert_faces || []);
		},
		faceState() {
			return this.isLeft
				? (this.item.left_state || 'alert')
				: (this.item.right_state || 'alert');
		},
		deleteButtonClass() {
			return this.isLeft ? 'checks-delete-button checks-delete-button-right' : 'checks-delete-button checks-delete-button-left';
		},
		syncButtonClass() {
			return this.isLeft ? 'checks-sync-button checks-sync-button-right' : 'checks-sync-button checks-sync-button-left';
		},
		positionButtonClass() {
			return this.isLeft ? 'checks-position-button checks-position-button-left' : 'checks-position-button checks-position-button-right';
		},
		positionTooltip() {
			return this.isLeft
				? this.vm.getChecksReplaceLeftTooltip(this.item)
				: this.vm.getChecksReplaceRightTooltip(this.item);
		},
		positionIconUrl() {
			return this.isLeft
				? this.vm.getChecksPositionLeftIconUrl()
				: this.vm.getChecksPositionRightIconUrl();
		},
		positionFallback() {
			return this.isLeft
				? this.vm.$avt('checks:button_replace_position_left', '<- Pos')
				: this.vm.$avt('checks:button_replace_position_right', 'Pos ->');
		},
	},
};
</script>
