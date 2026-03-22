<template>
  <nav class="mb-2 flex justify-between align-top md:mb-12">
    <RouterLink :to="{ name: 'home' }" v-if="!hideLogo">
      <Logo responsive></Logo>
    </RouterLink>
    <div class="flex grow items-start justify-end">
      <!-- New Note -->
      <RouterLink v-if="showNewButton" :to="{ name: 'new' }">
        <CustomButton :iconPath="mdilPlusCircle" label="New Note" />
      </RouterLink>
      <!-- Menu -->
      <CustomButton
        class="ml-1"
        :iconPath="mdilMenu"
        label="Menu"
        @click="toggleMenu"
      />
      <PrimeMenu ref="menu" :model="menuItems" :popup="true" />
    </div>
  </nav>
</template>

<script setup>
import {
  mdilClipboard,
  mdilLogout,
  mdilMagnify,
  mdilMenu,
  mdilMonitor,
  mdilNoteMultiple,
  mdilPlusCircle,
} from "@mdi/light-js";
import { useToast } from "primevue/usetoast";
import { computed, ref } from "vue";
import { RouterLink, useRouter } from "vue-router";

import CustomButton from "../components/CustomButton.vue";
import Logo from "../components/Logo.vue";
import PrimeMenu from "../components/PrimeMenu.vue";
import { authTypes, params, searchSortOptions } from "../constants.js";
import { useGlobalStore } from "../globalStore.js";
import { getToastOptions, toggleTheme } from "../helpers.js";
import { clearStoredToken, getStoredToken } from "../tokenStorage.js";

const globalStore = useGlobalStore();
const menu = ref();
const router = useRouter();
const toast = useToast();

defineProps({
  hideLogo: Boolean,
});

const emit = defineEmits(["toggleSearchModal"]);

const menuItems = [
  {
    label: "Search",
    icon: mdilMagnify,
    command: () => emit("toggleSearchModal"),
    keyboardShortcut: "/",
  },
  {
    label: "All Notes",
    icon: mdilNoteMultiple,
    command: () =>
      router.push({
        name: "search",
        query: {
          [params.searchTerm]: "*",
          [params.sortBy]: searchSortOptions.title,
        },
      }),
  },
  {
    label: "Toggle Theme",
    icon: mdilMonitor,
    command: toggleTheme,
  },
  {
    label: "Copy MCP Token",
    icon: mdilClipboard,
    command: copyMcpToken,
    visible: () => showLogOutButton() && !!getStoredToken(),
  },
  {
    separator: true,
    visible: showLogOutButton,
  },
  {
    label: "Log Out",
    icon: mdilLogout,
    command: logOut,
    visible: showLogOutButton,
  },
];

const showNewButton = computed(() => {
  return globalStore.config.authType !== authTypes.readOnly;
});

async function copyMcpToken() {
  const token = getStoredToken();
  try {
    await navigator.clipboard.writeText(token);
    toast.add(
      getToastOptions("Token copied to clipboard", "MCP Token", "success"),
    );
  } catch {
    // Fallback for non-HTTPS: show in a prompt so the user can copy manually
    prompt("Copy your MCP token:", token);
  }
}

function logOut() {
  clearStoredToken();
  localStorage.clear();
  router.push({ name: "login" });
}

function toggleMenu(event) {
  menu.value.toggle(event);
}

function showLogOutButton() {
  return ![authTypes.none, authTypes.readOnly].includes(
    globalStore.config.authType,
  );
}
</script>
