-- phpMyAdmin SQL Dump
-- version 5.2.2
-- https://www.phpmyadmin.net/
--
-- Host: localhost
-- Generation Time: Jun 09, 2025 at 07:15 PM
-- Server version: 10.11.13-MariaDB-0ubuntu0.24.04.1
-- PHP Version: 8.3.6

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";

--
-- Database: `Woolinator`
--
CREATE DATABASE IF NOT EXISTS `Woolinator` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
USE `Woolinator`;

-- --------------------------------------------------------

--
-- Table structure for table `birthdays`
--

CREATE TABLE IF NOT EXISTS `birthdays` (
  `user_id` bigint(20) NOT NULL,
  `guild_id` bigint(20) NOT NULL,
  `date` varchar(10) NOT NULL,
  UNIQUE KEY `unique_user_guild` (`user_id`,`guild_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `channels`
--

CREATE TABLE IF NOT EXISTS `channels` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `feature` varchar(64) NOT NULL,
  `guild_id` bigint(20) NOT NULL,
  `channel_id` bigint(20) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_feature_guild` (`feature`,`guild_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `prefixes`
--

CREATE TABLE IF NOT EXISTS `prefixes` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `is_guild` tinyint(1) NOT NULL,
  `entity_id` bigint(20) NOT NULL,
  `prefix` varchar(4) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `reminders`
--

CREATE TABLE IF NOT EXISTS `reminders` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` bigint(20) NOT NULL,
  `time_created` datetime NOT NULL,
  `time_expire` datetime NOT NULL,
  `content` varchar(2000) NOT NULL,
  `is_dm` tinyint(1) NOT NULL DEFAULT 0,
  `link` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `tags`
--

CREATE TABLE IF NOT EXISTS `tags` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` bigint(20) NOT NULL,
  `guild_id` bigint(20) NOT NULL,
  `created` datetime NOT NULL,
  `name` varchar(32) NOT NULL,
  `content` varchar(2000) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
COMMIT;
