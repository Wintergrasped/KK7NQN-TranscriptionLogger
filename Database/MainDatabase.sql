-- --------------------------------------------------------
-- Host:                         192.168.0.128
-- Server version:               10.11.11-MariaDB-0+deb12u1 - Debian 12
-- Server OS:                    debian-linux-gnu
-- HeidiSQL Version:             12.11.0.7065
-- --------------------------------------------------------

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET NAMES utf8 */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;


-- Dumping database structure for repeater
CREATE DATABASE IF NOT EXISTS `repeater` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci */;
USE `repeater`;

-- Dumping structure for table repeater.callsigns
CREATE TABLE IF NOT EXISTS `callsigns` (
  `ID` int(11) NOT NULL AUTO_INCREMENT,
  `callsign` varchar(16) NOT NULL DEFAULT '',
  `validated` tinyint(1) NOT NULL DEFAULT 0,
  `first_seen` datetime NOT NULL DEFAULT current_timestamp(),
  `last_seen` datetime NOT NULL DEFAULT current_timestamp(),
  `seen_count` int(11) NOT NULL DEFAULT 1,
  `original_timestamp` datetime DEFAULT current_timestamp(),
  `last_modified` timestamp NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`ID`),
  UNIQUE KEY `callsign` (`callsign`),
  KEY `idx_last_modified` (`last_modified`)
) ENGINE=InnoDB AUTO_INCREMENT=15038 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table repeater.callsign_activity_stats
CREATE TABLE IF NOT EXISTS `callsign_activity_stats` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `callsign` varchar(16) NOT NULL,
  `total_tx_segments` int(11) DEFAULT 0,
  `open_qso_count` int(11) DEFAULT 0,
  `net_count` int(11) DEFAULT 0,
  `ncs_count` int(11) DEFAULT 0,
  `avg_turn_length_s` decimal(10,3) DEFAULT NULL,
  `median_turn_length_s` decimal(10,3) DEFAULT NULL,
  `reply_ratio` decimal(7,4) DEFAULT NULL,
  `last_seen` datetime DEFAULT NULL,
  `updated_at` datetime NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_cas_callsign` (`callsign`),
  KEY `idx_cas_last_seen` (`last_seen`)
) ENGINE=InnoDB AUTO_INCREMENT=13680 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table repeater.callsign_log
CREATE TABLE IF NOT EXISTS `callsign_log` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `callsign` varchar(16) NOT NULL,
  `transcript_id` int(11) NOT NULL,
  `timestamp` datetime DEFAULT current_timestamp(),
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=46915 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table repeater.callsign_metric_reasons
CREATE TABLE IF NOT EXISTS `callsign_metric_reasons` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `callsign` varchar(16) NOT NULL,
  `metric_key` varchar(64) NOT NULL,
  `reason_text` text NOT NULL,
  `evidence` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`evidence`)),
  `model_run_id` int(11) DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_cmr_callsign_metric` (`callsign`,`metric_key`),
  KEY `idx_cmr_created` (`created_at`)
) ENGINE=InnoDB AUTO_INCREMENT=81966 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table repeater.callsign_profile
CREATE TABLE IF NOT EXISTS `callsign_profile` (
  `callsign_id` int(11) NOT NULL,
  `latest_topic` varchar(128) DEFAULT NULL,
  `favorite_topic` varchar(128) DEFAULT NULL,
  `nets` int(11) NOT NULL DEFAULT 0,
  `latest_net_name` varchar(128) DEFAULT NULL,
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`callsign_id`),
  KEY `idx_cp_latest_net` (`latest_net_name`),
  CONSTRAINT `fk_cp_callsign` FOREIGN KEY (`callsign_id`) REFERENCES `callsigns` (`ID`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table repeater.callsign_profiles
CREATE TABLE IF NOT EXISTS `callsign_profiles` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `callsign` varchar(16) NOT NULL,
  `window_start` datetime DEFAULT NULL,
  `window_end` datetime DEFAULT NULL,
  `latest_topic` varchar(256) DEFAULT NULL,
  `most_topic` varchar(256) DEFAULT NULL,
  `topic_coverage` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`topic_coverage`)),
  `summary` text DEFAULT NULL,
  `personal_summary` text DEFAULT NULL,
  `friendly_score` decimal(5,4) DEFAULT NULL,
  `serious_score` decimal(5,4) DEFAULT NULL,
  `focus_score` decimal(5,4) DEFAULT NULL,
  `helpful_score` decimal(5,4) DEFAULT NULL,
  `technical_score` decimal(5,4) DEFAULT NULL,
  `civility_score` decimal(5,4) DEFAULT NULL,
  `open_qso_count` int(11) DEFAULT 0,
  `net_count` int(11) DEFAULT 0,
  `ncs_count` int(11) DEFAULT 0,
  `open_vs_net_bias_score` decimal(6,3) DEFAULT NULL,
  `open_vs_net_bias_window` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`open_vs_net_bias_window`)),
  `confidence` decimal(5,4) DEFAULT NULL,
  `data_freshness` datetime DEFAULT NULL,
  `model_run_id` int(11) DEFAULT NULL,
  `updated_at` datetime NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `created_at` datetime NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_callsign_profiles_callsign` (`callsign`),
  KEY `idx_callsign_profiles_bias` (`open_vs_net_bias_score`),
  KEY `idx_callsign_profiles_updated` (`updated_at`),
  KEY `idx_callsign_profiles_model_run` (`model_run_id`)
) ENGINE=InnoDB AUTO_INCREMENT=13339 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table repeater.callsign_profile_history
CREATE TABLE IF NOT EXISTS `callsign_profile_history` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `callsign` varchar(16) NOT NULL,
  `model_run_id` int(11) DEFAULT NULL,
  `window_start` datetime DEFAULT NULL,
  `window_end` datetime DEFAULT NULL,
  `payload` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`payload`)),
  `created_at` datetime NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_cph_callsign_created` (`callsign`,`created_at`),
  KEY `idx_cph_model_run` (`model_run_id`)
) ENGINE=InnoDB AUTO_INCREMENT=13339 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table repeater.callsign_topics
CREATE TABLE IF NOT EXISTS `callsign_topics` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `net_id` int(11) DEFAULT NULL,
  `callsign` tinytext DEFAULT NULL,
  `callsign_id` int(11) NOT NULL,
  `topic` varchar(128) NOT NULL DEFAULT 'NONE',
  `topic_description` text DEFAULT NULL,
  `mentions` int(11) NOT NULL DEFAULT 0,
  `last_seen_time` datetime DEFAULT NULL,
  `confidence` float DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uniq_ct` (`callsign_id`) USING BTREE,
  KEY `idx_ct_topic` (`topic`),
  CONSTRAINT `fk_ct_callsign` FOREIGN KEY (`callsign_id`) REFERENCES `callsigns` (`ID`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=430 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table repeater.callsign_topic_events
CREATE TABLE IF NOT EXISTS `callsign_topic_events` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `callsign` varchar(20) NOT NULL,
  `transcript_id` int(11) NOT NULL,
  `event_time` datetime DEFAULT NULL,
  `topic` varchar(64) NOT NULL,
  `topic_confidence` tinyint(3) unsigned NOT NULL,
  `excerpt` varchar(512) DEFAULT NULL,
  `span_char_start` int(11) DEFAULT NULL,
  `span_char_end` int(11) DEFAULT NULL,
  `source` enum('LLM','AA','MIXED') NOT NULL DEFAULT 'LLM',
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_cte_callsign_time` (`callsign`,`event_time`),
  KEY `idx_cte_topic_time` (`topic`,`event_time`),
  KEY `idx_cte_transcript` (`transcript_id`),
  CONSTRAINT `fk_cte_transcript` FOREIGN KEY (`transcript_id`) REFERENCES `smoothed_transcripts` (`original_transcript_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=4613 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table repeater.callsign_topic_stats
CREATE TABLE IF NOT EXISTS `callsign_topic_stats` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `callsign` varchar(16) NOT NULL,
  `topic` varchar(256) NOT NULL,
  `count_total` int(11) DEFAULT 0,
  `count_open_qso` int(11) DEFAULT 0,
  `count_net` int(11) DEFAULT 0,
  `first_seen` datetime DEFAULT NULL,
  `last_seen` datetime DEFAULT NULL,
  `weight` decimal(7,4) DEFAULT NULL,
  `updated_at` datetime NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_cts_callsign_topic` (`callsign`,`topic`),
  KEY `idx_cts_weight` (`weight`),
  KEY `idx_cts_last_seen` (`last_seen`)
) ENGINE=InnoDB AUTO_INCREMENT=17471 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table repeater.clubs
CREATE TABLE IF NOT EXISTS `clubs` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(128) NOT NULL,
  `website` varchar(255) DEFAULT NULL,
  `qrz_url` varchar(255) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uniq_club_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table repeater.corrections
CREATE TABLE IF NOT EXISTS `corrections` (
  `detect` tinytext DEFAULT NULL,
  `correct` tinytext DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table repeater.extended_callsign_profile
CREATE TABLE IF NOT EXISTS `extended_callsign_profile` (
  `callsign` varchar(16) NOT NULL,
  `first_seen` datetime DEFAULT NULL,
  `last_seen` datetime DEFAULT NULL,
  `total_mentions` int(11) NOT NULL DEFAULT 0,
  `total_utterances` int(11) NOT NULL DEFAULT 0,
  `total_nets` int(11) NOT NULL DEFAULT 0,
  `avg_words_per_turn` float DEFAULT NULL,
  `topics_rollup_json` longtext DEFAULT NULL,
  `last_updated` timestamp NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`callsign`),
  KEY `idx_profile_last_seen` (`last_seen`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table repeater.ncs_metric_reasons
CREATE TABLE IF NOT EXISTS `ncs_metric_reasons` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `callsign` varchar(16) NOT NULL,
  `metric_key` varchar(64) NOT NULL,
  `reason_text` text NOT NULL,
  `evidence` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`evidence`)),
  `model_run_id` int(11) DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_nmr_callsign_metric` (`callsign`,`metric_key`),
  KEY `idx_nmr_created` (`created_at`)
) ENGINE=InnoDB AUTO_INCREMENT=928 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table repeater.ncs_profiles
CREATE TABLE IF NOT EXISTS `ncs_profiles` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `callsign` varchar(16) NOT NULL,
  `window_start` datetime DEFAULT NULL,
  `window_end` datetime DEFAULT NULL,
  `nets_led_count` int(11) DEFAULT 0,
  `nets_led_unique` int(11) DEFAULT 0,
  `avg_checkins` decimal(10,3) DEFAULT NULL,
  `avg_duration_min` decimal(10,3) DEFAULT NULL,
  `control_style_summary` text DEFAULT NULL,
  `friendliness_score` decimal(5,4) DEFAULT NULL,
  `structure_score` decimal(5,4) DEFAULT NULL,
  `inclusivity_score` decimal(5,4) DEFAULT NULL,
  `clarity_score` decimal(5,4) DEFAULT NULL,
  `civility_score` decimal(5,4) DEFAULT NULL,
  `confidence` decimal(5,4) DEFAULT NULL,
  `data_freshness` datetime DEFAULT NULL,
  `model_run_id` int(11) DEFAULT NULL,
  `updated_at` datetime NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `created_at` datetime NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ncs_profiles_callsign` (`callsign`),
  KEY `idx_ncs_profiles_updated` (`updated_at`),
  KEY `idx_ncs_profiles_model_run` (`model_run_id`)
) ENGINE=InnoDB AUTO_INCREMENT=187 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table repeater.ncs_profile_history
CREATE TABLE IF NOT EXISTS `ncs_profile_history` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `callsign` varchar(16) NOT NULL,
  `model_run_id` int(11) DEFAULT NULL,
  `window_start` datetime DEFAULT NULL,
  `window_end` datetime DEFAULT NULL,
  `payload` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`payload`)),
  `created_at` datetime NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_ncsh_callsign_created` (`callsign`,`created_at`),
  KEY `idx_ncsh_model_run` (`model_run_id`)
) ENGINE=InnoDB AUTO_INCREMENT=187 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table repeater.net_activity_stats
CREATE TABLE IF NOT EXISTS `net_activity_stats` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `net_slug` varchar(128) NOT NULL,
  `instances_count` int(11) DEFAULT 0,
  `total_checkins` int(11) DEFAULT 0,
  `avg_checkins` decimal(10,3) DEFAULT NULL,
  `avg_duration_min` decimal(10,3) DEFAULT NULL,
  `first_seen` datetime DEFAULT NULL,
  `last_seen` datetime DEFAULT NULL,
  `topic_coverage` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`topic_coverage`)),
  `updated_at` datetime NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_nas_net_slug` (`net_slug`),
  KEY `idx_nas_last_seen` (`last_seen`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table repeater.net_data
CREATE TABLE IF NOT EXISTS `net_data` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `net_name` varchar(255) DEFAULT NULL,
  `club_name` varchar(255) DEFAULT NULL,
  `ncs_callsign` varchar(16) DEFAULT NULL,
  `start_transcription_id` int(11) DEFAULT NULL,
  `end_transcription_id` int(11) DEFAULT NULL,
  `start_time` datetime DEFAULT NULL,
  `end_time` datetime DEFAULT NULL,
  `duration_sec` int(11) DEFAULT NULL,
  `confidence_score` float DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `summary` text DEFAULT NULL,
  `ai` int(11) NOT NULL DEFAULT 0,
  `stage` int(11) NOT NULL DEFAULT 0,
  `processed` int(11) NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  KEY `fk_nd_start_transcription` (`start_transcription_id`),
  KEY `fk_nd_end_transcription` (`end_transcription_id`),
  KEY `idx_nd_times` (`start_time`,`end_time`),
  KEY `idx_nd_names` (`net_name`,`club_name`),
  KEY `idx_nd_ncs` (`ncs_callsign`),
  CONSTRAINT `fk_nd_end_transcription` FOREIGN KEY (`end_transcription_id`) REFERENCES `transcriptions` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `fk_nd_start_transcription` FOREIGN KEY (`start_transcription_id`) REFERENCES `transcriptions` (`id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=825 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table repeater.net_metric_reasons
CREATE TABLE IF NOT EXISTS `net_metric_reasons` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `net_slug` varchar(128) NOT NULL,
  `metric_key` varchar(64) NOT NULL,
  `reason_text` text NOT NULL,
  `evidence` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`evidence`)),
  `model_run_id` int(11) DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_nmr_slug_metric` (`net_slug`,`metric_key`),
  KEY `idx_nmr_created` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table repeater.net_names
CREATE TABLE IF NOT EXISTS `net_names` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(128) NOT NULL,
  `club_id` int(11) DEFAULT NULL,
  `schedule` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`schedule`)),
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uniq_net_name` (`name`),
  KEY `fk_nn_club` (`club_id`),
  CONSTRAINT `fk_nn_club` FOREIGN KEY (`club_id`) REFERENCES `clubs` (`id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table repeater.net_participation
CREATE TABLE IF NOT EXISTS `net_participation` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `net_id` int(11) NOT NULL,
  `callsign_id` int(11) DEFAULT NULL,
  `callsign` varchar(16) DEFAULT NULL,
  `first_seen_time` datetime DEFAULT NULL,
  `last_seen_time` datetime DEFAULT NULL,
  `transmissions_count` int(11) NOT NULL DEFAULT 0,
  `talk_seconds` int(11) NOT NULL DEFAULT 0,
  `checkin_type` enum('normal','late','recheck','proxy','mobile','echolink','allstar','io','unknown') DEFAULT 'unknown',
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uniq_net_callsign` (`net_id`,`callsign_id`),
  KEY `fk_np_callsign` (`callsign_id`),
  KEY `idx_np_callsign` (`callsign`),
  KEY `idx_np_first_last` (`first_seen_time`,`last_seen_time`),
  CONSTRAINT `fk_np_callsign` FOREIGN KEY (`callsign_id`) REFERENCES `callsigns` (`ID`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `fk_np_net` FOREIGN KEY (`net_id`) REFERENCES `net_data` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=25790 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table repeater.net_profiles
CREATE TABLE IF NOT EXISTS `net_profiles` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `net_slug` varchar(128) NOT NULL,
  `display_name` varchar(256) NOT NULL,
  `window_start` datetime DEFAULT NULL,
  `window_end` datetime DEFAULT NULL,
  `canonical_summary` text DEFAULT NULL,
  `friendliness_score` decimal(5,4) DEFAULT NULL,
  `focus_score` decimal(5,4) DEFAULT NULL,
  `diversity_score` decimal(5,4) DEFAULT NULL,
  `activity_score` decimal(5,4) DEFAULT NULL,
  `helpfulness_score` decimal(5,4) DEFAULT NULL,
  `civility_score` decimal(5,4) DEFAULT NULL,
  `typical_duration_min` int(11) DEFAULT NULL,
  `typical_checkins` int(11) DEFAULT NULL,
  `schedule_hint` varchar(256) DEFAULT NULL,
  `topic_coverage` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`topic_coverage`)),
  `confidence` decimal(5,4) DEFAULT NULL,
  `data_freshness` datetime DEFAULT NULL,
  `model_run_id` int(11) DEFAULT NULL,
  `updated_at` datetime NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `created_at` datetime NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_net_profiles_slug` (`net_slug`),
  KEY `idx_net_profiles_updated` (`updated_at`),
  KEY `idx_net_profiles_model_run` (`model_run_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table repeater.net_profile_history
CREATE TABLE IF NOT EXISTS `net_profile_history` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `net_slug` varchar(128) NOT NULL,
  `model_run_id` int(11) DEFAULT NULL,
  `window_start` datetime DEFAULT NULL,
  `window_end` datetime DEFAULT NULL,
  `payload` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`payload`)),
  `created_at` datetime NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_nph_slug_created` (`net_slug`,`created_at`),
  KEY `idx_nph_model_run` (`model_run_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table repeater.net_session_transcripts
CREATE TABLE IF NOT EXISTS `net_session_transcripts` (
  `ID` int(11) NOT NULL AUTO_INCREMENT,
  `net_id` int(11) NOT NULL,
  `transcription_id` int(11) NOT NULL,
  PRIMARY KEY (`net_id`,`transcription_id`,`ID`) USING BTREE,
  UNIQUE KEY `ID` (`ID`),
  KEY `idx_nst_transcription` (`transcription_id`),
  CONSTRAINT `fk_nst_net` FOREIGN KEY (`net_id`) REFERENCES `net_data` (`id`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `fk_nst_transcription` FOREIGN KEY (`transcription_id`) REFERENCES `transcriptions` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=34979 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table repeater.processing_tracking
CREATE TABLE IF NOT EXISTS `processing_tracking` (
  `ID` int(11) NOT NULL AUTO_INCREMENT,
  `transcript_id` int(11) NOT NULL DEFAULT 0,
  `regex_stage` int(11) NOT NULL DEFAULT 0,
  `ai_stage` int(11) NOT NULL DEFAULT 0,
  `data_stage` int(11) NOT NULL DEFAULT 0,
  PRIMARY KEY (`ID`),
  UNIQUE KEY `ID` (`ID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table repeater.profile_features
CREATE TABLE IF NOT EXISTS `profile_features` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `entity_type` enum('callsign','net','ncs') NOT NULL,
  `entity_key` varchar(128) NOT NULL,
  `feature_key` varchar(128) NOT NULL,
  `feature_payload` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`feature_payload`)),
  `model_run_id` int(11) DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT current_timestamp(),
  `updated_at` datetime NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_pf_entity_feature` (`entity_type`,`entity_key`,`feature_key`),
  KEY `idx_pf_model_run` (`model_run_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table repeater.profile_model_runs
CREATE TABLE IF NOT EXISTS `profile_model_runs` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `run_uuid` char(36) NOT NULL,
  `model_name` varchar(128) NOT NULL,
  `model_params` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`model_params`)),
  `prompt_hash` char(64) NOT NULL,
  `code_version` varchar(64) DEFAULT NULL,
  `started_at` datetime NOT NULL DEFAULT current_timestamp(),
  `finished_at` datetime DEFAULT NULL,
  `notes` text DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_profile_model_runs_run_uuid` (`run_uuid`),
  KEY `idx_profile_model_runs_started` (`started_at`)
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table repeater.smoothed_transcripts
CREATE TABLE IF NOT EXISTS `smoothed_transcripts` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `original_transcript_id` int(11) NOT NULL,
  `smoothed_text` mediumtext DEFAULT NULL,
  `callsigns_json` longtext NOT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `original_transcript_id` (`original_transcript_id`),
  CONSTRAINT `fk_smoothed_transcripts_src` FOREIGN KEY (`original_transcript_id`) REFERENCES `transcriptions` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=35915 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table repeater.system_stats
CREATE TABLE IF NOT EXISTS `system_stats` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `device_name` varchar(50) DEFAULT NULL,
  `timestamp` datetime NOT NULL,
  `cpu_usage` float DEFAULT NULL,
  `memory_usage` float DEFAULT NULL,
  `cpu_temp` float DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=215136 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table repeater.temperature_log
CREATE TABLE IF NOT EXISTS `temperature_log` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `sensor_id` varchar(32) DEFAULT NULL,
  `temperature_c` float DEFAULT NULL,
  `temperature_f` float DEFAULT NULL,
  `timestamp` datetime DEFAULT current_timestamp(),
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=330037 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table repeater.topics
CREATE TABLE IF NOT EXISTS `topics` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `topic` varchar(128) NOT NULL,
  `description` text DEFAULT NULL,
  `keywords` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`keywords`)),
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uniq_topic` (`topic`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table repeater.transcriptions
CREATE TABLE IF NOT EXISTS `transcriptions` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `filename` varchar(255) NOT NULL,
  `transcription` text DEFAULT NULL,
  `timestamp` datetime DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `processed` tinyint(1) NOT NULL DEFAULT 0,
  `analyzed` tinyint(4) DEFAULT 0,
  PRIMARY KEY (`id`),
  KEY `idx_transcriptions_analyzed` (`analyzed`)
) ENGINE=InnoDB AUTO_INCREMENT=46048 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table repeater.transcriptions_large
CREATE TABLE IF NOT EXISTS `transcriptions_large` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `filename` varchar(255) NOT NULL,
  `transcription` text DEFAULT NULL,
  `timestamp` datetime DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `processed` tinyint(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci ROW_FORMAT=DYNAMIC;

-- Data exporting was unselected.

-- Dumping structure for table repeater.transcription_analysis
CREATE TABLE IF NOT EXISTS `transcription_analysis` (
  `ID` int(11) NOT NULL AUTO_INCREMENT,
  `transcription_id` int(11) NOT NULL,
  `is_net` tinyint(1) NOT NULL DEFAULT 0,
  `net_id` int(11) DEFAULT NULL,
  `ncs_candidate` tinyint(1) NOT NULL DEFAULT 0,
  `detected_net_name` varchar(255) DEFAULT NULL,
  `detected_club_name` varchar(255) DEFAULT NULL,
  `keyword_hits` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`keyword_hits`)),
  `callsigns_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`callsigns_json`)),
  `topic_labels` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`topic_labels`)),
  `confidence_score` float DEFAULT NULL,
  `analyzed_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`transcription_id`),
  UNIQUE KEY `ID` (`ID`),
  KEY `idx_ta_isnet` (`is_net`),
  KEY `idx_ta_netid` (`net_id`),
  KEY `idx_ta_detected_net_name` (`detected_net_name`),
  KEY `idx_ta_detected_club_name` (`detected_club_name`),
  CONSTRAINT `fk_ta_transcription` FOREIGN KEY (`transcription_id`) REFERENCES `transcriptions` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=45557 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for view repeater.vw_callsign_net_open_bias
-- Creating temporary table to overcome VIEW dependency errors
CREATE TABLE `vw_callsign_net_open_bias` (
	`callsign` VARCHAR(1) NOT NULL COLLATE 'utf8mb4_general_ci',
	`open_qso_count` INT(11) NULL,
	`net_count` INT(11) NULL,
	`net_over_open_ratio` DECIMAL(15,4) NULL,
	`open_vs_net_bias_score` DECIMAL(6,3) NULL,
	`updated_at` DATETIME NOT NULL
);

-- Dumping structure for view repeater.vw_callsign_top_topics
-- Creating temporary table to overcome VIEW dependency errors
CREATE TABLE `vw_callsign_top_topics` (
	`callsign` VARCHAR(1) NOT NULL COLLATE 'utf8mb4_general_ci',
	`topic` VARCHAR(1) NOT NULL COLLATE 'utf8mb4_general_ci',
	`weight` DECIMAL(7,4) NULL,
	`count_total` INT(11) NULL,
	`last_seen` DATETIME NULL
);

-- Dumping structure for view repeater.v_net_roster
-- Creating temporary table to overcome VIEW dependency errors
CREATE TABLE `v_net_roster` (
	`net_id` INT(11) NOT NULL,
	`net_name` VARCHAR(1) NULL COLLATE 'utf8mb4_general_ci',
	`club_name` VARCHAR(1) NULL COLLATE 'utf8mb4_general_ci',
	`start_time` DATETIME NULL,
	`end_time` DATETIME NULL,
	`callsign` VARCHAR(1) NULL COLLATE 'utf8mb4_general_ci',
	`transmissions_count` INT(11) NOT NULL,
	`talk_seconds` INT(11) NOT NULL,
	`checkin_type` ENUM('normal','late','recheck','proxy','mobile','echolink','allstar','io','unknown') NULL COLLATE 'utf8mb4_general_ci'
);

-- Dumping structure for view repeater.v_net_slug
-- Creating temporary table to overcome VIEW dependency errors
CREATE TABLE `v_net_slug` (
	`net_id` INT(11) NOT NULL,
	`net_slug` VARCHAR(1) NULL COLLATE 'utf8mb4_general_ci',
	`net_name` VARCHAR(1) NULL COLLATE 'utf8mb4_general_ci',
	`club_name` VARCHAR(1) NULL COLLATE 'utf8mb4_general_ci'
);

-- Removing temporary table and create final VIEW structure
DROP TABLE IF EXISTS `vw_callsign_net_open_bias`;
CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `vw_callsign_net_open_bias` AS select `cp`.`callsign` AS `callsign`,`cas`.`open_qso_count` AS `open_qso_count`,`cas`.`net_count` AS `net_count`,(`cas`.`net_count` + 1) / (`cas`.`open_qso_count` + 1) AS `net_over_open_ratio`,`cp`.`open_vs_net_bias_score` AS `open_vs_net_bias_score`,`cp`.`updated_at` AS `updated_at` from (`callsign_profiles` `cp` left join `callsign_activity_stats` `cas` on(`cas`.`callsign` = `cp`.`callsign`))
;

-- Removing temporary table and create final VIEW structure
DROP TABLE IF EXISTS `vw_callsign_top_topics`;
CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `vw_callsign_top_topics` AS select `cts`.`callsign` AS `callsign`,`cts`.`topic` AS `topic`,`cts`.`weight` AS `weight`,`cts`.`count_total` AS `count_total`,`cts`.`last_seen` AS `last_seen` from `callsign_topic_stats` `cts` where `cts`.`weight` is not null order by `cts`.`weight` desc
;

-- Removing temporary table and create final VIEW structure
DROP TABLE IF EXISTS `v_net_roster`;
CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `v_net_roster` AS select `nd`.`id` AS `net_id`,`nd`.`net_name` AS `net_name`,`nd`.`club_name` AS `club_name`,`nd`.`start_time` AS `start_time`,`nd`.`end_time` AS `end_time`,`np`.`callsign` AS `callsign`,`np`.`transmissions_count` AS `transmissions_count`,`np`.`talk_seconds` AS `talk_seconds`,`np`.`checkin_type` AS `checkin_type` from (`net_data` `nd` join `net_participation` `np` on(`np`.`net_id` = `nd`.`id`))
;

-- Removing temporary table and create final VIEW structure
DROP TABLE IF EXISTS `v_net_slug`;
CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `v_net_slug` AS select `nd`.`id` AS `net_id`,lcase(replace(replace(concat_ws('::',coalesce(`nd`.`club_name`,''),coalesce(`nd`.`net_name`,'')),' ','-'),'/','-')) AS `net_slug`,`nd`.`net_name` AS `net_name`,`nd`.`club_name` AS `club_name` from `net_data` `nd`
;

/*!40103 SET TIME_ZONE=IFNULL(@OLD_TIME_ZONE, 'system') */;
/*!40101 SET SQL_MODE=IFNULL(@OLD_SQL_MODE, '') */;
/*!40014 SET FOREIGN_KEY_CHECKS=IFNULL(@OLD_FOREIGN_KEY_CHECKS, 1) */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40111 SET SQL_NOTES=IFNULL(@OLD_SQL_NOTES, 1) */;
