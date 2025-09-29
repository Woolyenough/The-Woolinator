-- phpMyAdmin SQL Dump
-- version 5.2.2
-- https://www.phpmyadmin.net/
--
-- Host: localhost
-- Generation Time: Sep 29, 2025 at 11:48 AM
-- Server version: 10.11.13-MariaDB-0ubuntu0.24.04.1
-- PHP Version: 8.3.6

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Database: `Woolinator`
--

-- --------------------------------------------------------

--
-- Table structure for table `birthdays`
--

CREATE TABLE `birthdays` (
  `user_id` bigint(20) UNSIGNED NOT NULL,
  `guild_id` bigint(20) UNSIGNED NOT NULL,
  `date` varchar(10) NOT NULL,
  `last_announced` smallint(5) UNSIGNED DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `channels`
--

CREATE TABLE `channels` (
  `id` int(11) NOT NULL,
  `feature` varchar(64) NOT NULL,
  `guild_id` bigint(20) UNSIGNED NOT NULL,
  `channel_id` bigint(20) UNSIGNED NOT NULL,
  `fails` smallint(5) UNSIGNED NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `prefixes`
--

CREATE TABLE `prefixes` (
  `id` int(11) NOT NULL,
  `is_guild` tinyint(1) NOT NULL,
  `entity_id` bigint(20) UNSIGNED NOT NULL,
  `prefix` varchar(4) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `reminders`
--

CREATE TABLE `reminders` (
  `id` int(11) NOT NULL,
  `user_id` bigint(20) UNSIGNED NOT NULL,
  `time_created` datetime NOT NULL,
  `time_expire` datetime NOT NULL,
  `content` varchar(2000) NOT NULL,
  `is_dm` tinyint(1) NOT NULL DEFAULT 0,
  `link` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `tags`
--

CREATE TABLE `tags` (
  `id` int(11) NOT NULL,
  `user_id` bigint(20) UNSIGNED NOT NULL,
  `guild_id` bigint(20) UNSIGNED NOT NULL,
  `created` datetime NOT NULL,
  `name` varchar(32) NOT NULL,
  `content` varchar(2000) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Indexes for dumped tables
--

--
-- Indexes for table `birthdays`
--
ALTER TABLE `birthdays`
  ADD UNIQUE KEY `unique_user_guild` (`user_id`,`guild_id`);

--
-- Indexes for table `channels`
--
ALTER TABLE `channels`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `unique_feature_guild` (`feature`,`guild_id`);

--
-- Indexes for table `prefixes`
--
ALTER TABLE `prefixes`
  ADD PRIMARY KEY (`id`);

--
-- Indexes for table `reminders`
--
ALTER TABLE `reminders`
  ADD PRIMARY KEY (`id`);

--
-- Indexes for table `tags`
--
ALTER TABLE `tags`
  ADD PRIMARY KEY (`id`);

--
-- AUTO_INCREMENT for dumped tables
--

--
-- AUTO_INCREMENT for table `channels`
--
ALTER TABLE `channels`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `prefixes`
--
ALTER TABLE `prefixes`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `reminders`
--
ALTER TABLE `reminders`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `tags`
--
ALTER TABLE `tags`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
